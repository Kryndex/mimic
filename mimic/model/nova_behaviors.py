"""
Custom behaviors for the nova mimic.
"""
from json import dumps
from characteristic import attributes, Attribute
from mimic.util.helper import invalid_resource

@attributes([Attribute("behaviors", default_factory=dict)])
class BehaviorLookup(object):
    """
    A collection of behaviors with a related schema.
    """

    def behavior_creator(self, name):
        """
        Decorator which declares the decorated function is a behavior for this
        table.
        """
        def decorator(thunk):
            thunk.behavior_name = name
            self.behaviors[name] = thunk
            return thunk
        return decorator

    def create_behavior(self, name, params):
        """
        Create behavior identified by the given name, with the given
        parameters.  This is used during the process of registering a behavior.

        :param params: An object (deserialized from JSON) which serves as
            parameters to the named behavior creator.
        """
        return self.behaviors[name](params)


server_creation = BehaviorLookup()

@server_creation.behavior("fail")
def create_fail_behavior(parameters):
    """
    Create a failing behavior for server creation.
    """
    status_code = parameters.get("code", 500)
    failure_message = parameters.get("message", "Server creation failed.")
    def fail_without_creating(collection, http, json, absolutize_url):
        # behavior for failing to even start to build
        http.setResponseCode(status_code)
        return dumps(invalid_resource(failure_message, status_code))
    return fail_without_creating
