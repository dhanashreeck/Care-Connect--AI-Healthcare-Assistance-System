from db import cursor

# Test a simple query
cursor.execute("SHOW TABLES;")
tables = cursor.fetchall()
print("Tables in healthcare_db:", tables)
