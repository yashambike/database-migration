from mysql.connector import pooling
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "admin",
    "port": 3306
}

pool = pooling.MySQLConnectionPool(
    pool_name="my_pool",
    pool_size=5,  # Adjust the pool size as needed
    **db_config
)