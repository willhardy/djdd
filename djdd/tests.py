#!/usr/bin/env python

import unittest
from djdd.base import BuildEnvironment, format_database_connection, logger
from djdd import exceptions

TEST_DATABASE = "postgres:///djdd_test"
TEST_DIR = "djdd-test-dir"


class BuildEnvironmentTests(unittest.TestCase):
    def test_basic(self):
        build_env = BuildEnvironment(dir=TEST_DIR, variant_database=TEST_DATABASE)
        self.assertEqual(build_env.has_config_link, False)
        self.assertEqual(build_env.has_config, False)

    def test_format_database_connection(self):
        """ Check that the database definition strings we need are parsed correctly. """
        build_env = BuildEnvironment(dir=TEST_DIR, variant_database=TEST_DATABASE)
        CONN_STRINGS = [
            ('postgres://localhost/dbname', 'postgres://localhost/dbname'),
            ('postgres://user@localhost:1234/dbname', 'postgres://user@localhost:1234/dbname'),
            ('postgres://user:password@localhost:1234/dbname', 'postgres://user:XXXXX@localhost:1234/dbname'),
        ]
        for uri, exp_output in CONN_STRINGS:
            conn = build_env.parse_database_uri(uri)
            self.assertEqual(format_database_connection(conn), exp_output)

    def test_parse_database_uri(self):
        """ Check that the database definition strings we need are parsed correctly. """
        build_env = BuildEnvironment(dir=TEST_DIR, variant_database=TEST_DATABASE)
        VALID_STRINGS = [
                'postgres:///dbname',
                'postgres://localhost/dbname',
                'postgres://user:password@localhost:1234/dbname',
        ]
        INVALID_STRINGS = [
                'mysql://localhost/dbname',
                'localhost/dbname',
                'postgres://localhost:badport/dbname',
        ]
        for database in VALID_STRINGS:
            # XXX assert something here
            build_env.parse_database_uri(database)
        for database in INVALID_STRINGS:
            with self.assertRaises(exceptions.BuildEnvironmentError):
                build_env.parse_database_uri(database)

    def test_variant_db(self):
        build_env = BuildEnvironment(dir=TEST_DIR, variant_database=TEST_DATABASE)
        build_env.create_variant_database()

        # Typical use case: get the next available ID
        # create a variant for that and use it
        vid = build_env.get_next_variant_id()
        info = {
                'id': vid,
                'software': 'software',
                'key': 'berlin',
                'name': 'Berlin',
                'subdomain': 'berlin',
                'postgres_name': 'berlin',
                'elasticsearch_name': 'berlin',
                'redis_number': vid,
                'gunicorn_port': 4000 + vid,
                }
        # Put some basic information into the database
        self.assertEqual(build_env.set_variant_info('software', 'berlin', info), True)
        # Check that the same information comes out of the database
        self.assertEqual(build_env.get_variant_info('software', 'berlin'), info)

    def tearDown(self):
        build_env = BuildEnvironment(dir=TEST_DIR, variant_database=TEST_DATABASE)
        query = "TRUNCATE variant; COMMIT"
        curs = build_env.conn.cursor()
        logger.debug("Truncating variant table (end of test)")
        curs.execute(query)

if __name__ == "__main__":
    unittest.main()
