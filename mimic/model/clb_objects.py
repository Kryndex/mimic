"""
Model objects for the CLB mimic.
"""

from mimic.util.helper import (not_found_response, seconds_to_timestamp,
                               EMPTY_RESPONSE)
from twisted.python import log
from characteristic import attributes, Attribute
from mimic.canned_responses.loadbalancer import (load_balancer_example,
                                                 _verify_and_update_lb_state,
                                                 _lb_without_tenant,
                                                 _prep_for_list,
                                                 _delete_node)


class RegionalCLBCollection(object):
    """
    A collection of CloudLoadBalancers, in a given region, for a given tenant.
    """
    def __init__(self):
        """
        There are two stores - the lb info, and the metadata info
        """
        self.lbs = {}
        self.meta = {}

    def add_load_balancer(self, tenant_id, lb_info, lb_id, current_timestamp):
        """
        Returns response of a newly created load balancer with
        response code 202, and adds the new lb to the store's lbs.
        Note: ``store.lbs`` has tenant_id added as an extra key in comparison
        to the lb_example.

        :param string tenant_id: Tenant ID who will own this load balancer.
        :param dict lb_info: Configuration for the load balancer.  See
            Openstack docs for creating CLBs.
        :param string lb_id: Unique ID for this load balancer.
        :param float current_timestamp: The time since epoch when the CLB is
            created, measured in seconds.
        """
        status = "ACTIVE"

        # Loadbalancers metadata is a list object, creating a metadata store
        # so we dont have to deal with the list
        meta = {}
        if "metadata" in lb_info:
            for each in lb_info["metadata"]:
                meta.update({each["key"]: each["value"]})
        self.meta[lb_id] = meta
        log.msg(self.meta)

        if "lb_building" in self.meta[lb_id]:
            status = "BUILD"

        # Add tenant_id and nodeCount to self.lbs
        current_timestring = seconds_to_timestamp(current_timestamp)
        self.lbs[lb_id] = load_balancer_example(lb_info, lb_id, status,
                                                current_timestring)
        self.lbs[lb_id].update({"tenant_id": tenant_id})
        self.lbs[lb_id].update(
            {"nodeCount": len(self.lbs[lb_id].get("nodes", []))})

        # and remove before returning response for add lb
        new_lb = _lb_without_tenant(self, lb_id)

        return {'loadBalancer': new_lb}, 202

    def get_load_balancers(self, lb_id, current_timestamp):
        """
        Returns the load balancers with the given lb id, with response
        code 200. If no load balancers are found returns 404.
        """
        if lb_id in self.lbs:
            _verify_and_update_lb_state(self, lb_id, False, current_timestamp)
            log.msg(self.lbs[lb_id]["status"])
            new_lb = _lb_without_tenant(self, lb_id)
            return {'loadBalancer': new_lb}, 200
        return not_found_response("loadbalancer"), 404

    def list_load_balancers(self, tenant_id, current_timestamp):
        """
        Returns the list of load balancers with the given tenant id with response
        code 200. If no load balancers are found returns empty list.
        """
        response = dict(
            (k, v) for (k, v) in self.lbs.items()
            if tenant_id == v['tenant_id']
        )
        for each in response:
            _verify_and_update_lb_state(self, each, False, current_timestamp)
            log.msg(self.lbs[each]["status"])
        updated_resp = dict(
            (k, v) for (k, v) in self.lbs.items()
            if tenant_id == v['tenant_id']
        )
        return {'loadBalancers': _prep_for_list(updated_resp.values()) or []}, 200

    def delete_nodes(self, lb_id, node_ids, current_timestamp):
        """
        Bulk-delete multiple LB nodes.
        """
        if not node_ids:
            resp = {
                "message": "Must supply one or more id's to process this request.",
                "code": 400}
            return resp, 400

        if lb_id not in self.lbs:
            return not_found_response("loadbalancer"), 404

        _verify_and_update_lb_state(self, lb_id, False, current_timestamp)

        if self.lbs[lb_id]["status"] != "ACTIVE":
            # Error message verified as of 2015-04-22
            resp = {"message": "LoadBalancer is not ACTIVE",
                    "code": 422}
            return resp, 422

        # We need to verify all the deletions up front, and only allow it through
        # if all of them are valid.
        all_ids = [node["id"] for node in self.lbs[lb_id].get("nodes", [])]
        non_nodes = set(node_ids).difference(all_ids)
        if non_nodes:
            nodes = ','.join(map(str, non_nodes))
            resp = {
                "validationErrors": {
                    "messages": [
                        "Node ids {0} are not a part of your loadbalancer".format(nodes)
                    ]
                },
                "message": "Validation Failure",
                "code": 400,
                "details": "The object is not valid"}
            return resp, 400

        for node_id in node_ids:
            # It should not be possible for this to fail, since we've already
            # checked that they all exist.
            assert _delete_node(self, lb_id, node_id) is True

        _verify_and_update_lb_state(self, lb_id,
                                    current_timestamp=current_timestamp)
        return EMPTY_RESPONSE, 202


@attributes(["tenant_id", "clock",
             Attribute("regional_collections", default_factory=dict)])
class GlobalCLBCollections(object):
    """
    A :obj:`GlobalCLBCollections` is a set of all the
    :obj:`RegionalCLBCollection` objects owned by a given tenant.  In other
    words, all the objects that a single tenant owns globally in a
    cloud load balancer service.
    """

    def collection_for_region(self, region_name):
        """
        Get a :obj:`RegionalCLBCollection` for the region identified by the
        given name.
        """
        if region_name not in self.regional_collections:
            self.regional_collections[region_name] = (
                RegionalCLBCollection()
            )
        return self.regional_collections[region_name]
