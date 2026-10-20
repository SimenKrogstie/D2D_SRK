"""Storing and extracting the cross-border flows in a local Cassandra database with Spark."""

import os
import subprocess
import sys
import time

import pandas as pd


class SparkCassandra:
    """Spark session connected to Cassandra, plus the schema for the flow table."""

    CONNECTOR = "com.datastax.spark:spark-cassandra-connector_2.12:3.5.1"
    KEYSPACE = "ind320"
    TABLE = "cross_border_flows"

    # Columns extracted from Cassandra for the plots and MongoDB
    COLUMNS = ["connection", "direction", "from_zone", "to_zone", "year", "time", "flow_mw", "energy_mwh"]

    def __init__(self, host: str = "localhost", port: int = 9042):
        self.host = host
        self.port = port
        self.session = None  # set in create_schema()
        self.cluster = None
        self.spark = None

    @staticmethod
    def configure_environment() -> None:
        """Set the environment variables Spark needs, as described in the course book."""
        if "JAVA_HOME" not in os.environ:
            os.environ["JAVA_HOME"] = subprocess.check_output(
                ["/usr/libexec/java_home", "-v", "17"], text=True
            ).strip()

        # Use same Python as in notebook
        os.environ["PYSPARK_PYTHON"] = sys.executable
        os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
        os.environ["PYSPARK_HADOOP_VERSION"] = "without"

        # Spark reads time as local time. Making the process run in utc
        os.environ["TZ"] = "UTC"
        time.tzset()

    def create_schema(self) -> None:
        """Create the keyspace and table.

        Key ((connection, year), direction, time): one partition per
        connection and year, sorted by direction and time. Rewriting rows
        overwrites instead of duplicating.
        """
        from cassandra.cluster import Cluster

        self.cluster = Cluster([self.host], port=self.port)
        self.session = self.cluster.connect()

        # A single node, so replication factor 1 is enough
        self.session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {self.KEYSPACE}
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
        """)
        self.session.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.KEYSPACE}.{self.TABLE} (
                connection text,
                year int,
                direction text,
                time timestamp,
                from_zone text,
                to_zone text,
                flow_mw double,
                energy_mwh double,
                PRIMARY KEY ((connection, year), direction, time)
            )
        """)

    def start_spark(self):
        """Start a Spark session with the Cassandra connector."""
        from pyspark.sql import SparkSession

        self.configure_environment()
        self.spark = (
            SparkSession.builder.appName("IND320")
            .config("spark.jars.packages", self.CONNECTOR)
            .config("spark.cassandra.connection.host", self.host)
            .config("spark.cassandra.connection.port", str(self.port))
            .config("spark.sql.extensions", "com.datastax.spark.connector.CassandraSparkExtensions")
            # Keep timestamps in UTC
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
            .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            .getOrCreate()
        )
        return self.spark

    def _reader(self):
        return self.spark.read.format("org.apache.spark.sql.cassandra").options(
            table=self.TABLE, keyspace=self.KEYSPACE
        )

    def write(self, df: pd.DataFrame) -> int:
        """Convert a pandas DataFrame to Spark and append it to the Cassandra table."""
        sdf = self.spark.createDataFrame(df)    # Types inferred from pandas
        # "append" writes each row by its primary key, so rows that already exist are
        # overwritten instead of duplicated
        (
            sdf.write.format("org.apache.spark.sql.cassandra")
            .options(table=self.TABLE, keyspace=self.KEYSPACE)
            .mode("append")
            .save()
        )
        return sdf.count()

    def read(self):
        """Spark DataFrame with the relevant columns, plus a month column used by the app."""
        from pyspark.sql import functions as F

        return self._reader().load().select(*self.COLUMNS).withColumn("month", F.month("time"))

    def stop(self) -> None:
        if self.spark is not None:
            self.spark.stop()
        if self.cluster is not None:
            self.cluster.shutdown()
