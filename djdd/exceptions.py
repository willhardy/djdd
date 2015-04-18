class BuildEnvironmentError(Exception):
    def __init__(self, msg, build_env):
        self.msg = msg
        self.build_env = build_env

    def __str__(self):
        return "{}({})".format(self.__class__.__name__, repr(self.msg))


class VariantDBConnectionError(BuildEnvironmentError):
    def __init__(self, connection, build_env):
        self.connection = connection
        self.msg = "Could not connect to database \"{}\"".format(connection)
        self.build_env = build_env
