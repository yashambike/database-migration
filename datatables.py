from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
import os
import mysql.connector
import pandas as pd
import secrets
from config import db_config


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

@app.route('/show_databases')
def show_databases():
    db_conn = mysql.connector.connect(**db_config)
    cursor = db_conn.cursor()
    cursor.execute("SHOW DATABASES;")
    databases = [row[0] for row in cursor.fetchall()]
    db_conn.close()

    return render_template('show_databases.html', databases=databases)


@app.route('/datatables')
def index():
    return render_template('datatables.html')

@app.route('/api/get_databases', methods=['GET'])
def get_databases():
    db_conn = mysql.connector.connect(**db_config)
    cursor = db_conn.cursor()
    cursor.execute("SHOW DATABASES;")
    databases = [row[0] for row in cursor.fetchall()]
    db_conn.close()
    return jsonify(databases)

@app.route('/api/get_tables/<db_name>', methods=['GET'])
def get_tables(db_name):
    db_conn = mysql.connector.connect(database=db_name, **db_config)
    cursor = db_conn.cursor()
    cursor.execute("SHOW TABLES;")
    tables = [row[0] for row in cursor.fetchall()]
    db_conn.close()
    return jsonify(tables)

@app.route('/api/get_table_data/<db_name>/<table_name>', methods=['GET'])
def get_table_data(db_name, table_name):
    db_conn = mysql.connector.connect(database=db_name, **db_config)
    cursor = db_conn.cursor()
    cursor.execute(f"SELECT * FROM `{table_name}`")
    data = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    # Insert the column names as the first row in the data
    data.insert(0, columns)

    db_conn.close()
    return jsonify(data=data)



@app.route('/delete_database', methods=['POST'])
def delete_database():
    db_name = request.form['db_name']
    try:
        drop_database_function(db_name, db_config)
        flash(f"Database '{db_name}' dropped successfully!", "success")
    except Exception as e:
        flash(f"Failed to drop database '{db_name}': {str(e)}", "error")

    return redirect('/drop_database')

@app.route('/drop_database', methods=['GET', 'POST'])
def drop_database():
    db_list = get_database_list()

    if request.method == 'POST':
        db_name = request.form['db_name']
        try:
            drop_database_function(db_name, **db_config)
            flash("Database dropped successfully!", "success")
            db_list = get_database_list()  # Update the database list
        except Exception as e:
            flash(f"Failed to drop database: {str(e)}", "error")

    return render_template('drop_databases.html', db_list=db_list)


def get_database_list():
    db_conn = mysql.connector.connect(**db_config)
    cursor = db_conn.cursor()

    try:
        cursor.execute("SHOW DATABASES")
        database_list = [row[0] for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        # Handle the error (e.g., log it or return an empty list)
        print(f"Error fetching database list: {str(err)}")
        database_list = []

    cursor.close()
    db_conn.close()

    return database_list


def drop_database_function(db_name, db_config):
    db_conn = None
    cursor = None

    try:
        db_conn = mysql.connector.connect(**db_config)
        cursor = db_conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name};")
        db_conn.commit()
    except mysql.connector.Error as err:
        raise err
    finally:
        if cursor:
            cursor.close()
        if db_conn:
            db_conn.close()

if __name__ == '__main__':
    app.run(debug=True)