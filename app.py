from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
import os
import mysql.connector
import pandas as pd
import secrets
from config import db_config
import spacy
import logging

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Load spaCy NLP model
nlp = spacy.load("en_core_web_sm")
# Database connection settings

stemmer = PorterStemmer()

# Function to stem a keyword
def stem_keyword(keyword):
    return stemmer.stem(keyword)

@app.route('/homepage')
def homepage():
    return render_template('index.html')

def create_database(db_name):
    db_conn = None
    cursor = None
    try:
        db_conn = mysql.connector.connect(**db_config)
        cursor = db_conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name};")
        db_conn.commit()
    except mysql.connector.Error as err:
        flash(f"Database creation failed: {str(err)}", "error")
    finally:
        if cursor:
            cursor.close()
        if db_conn:
            db_conn.close()

def get_mysql_data_type(pandas_dtype):
    data_type_mapping = {
        'int64': 'INT',
        'float64': 'DOUBLE',
        'object': 'TEXT',  # Default to TEXT for other data types
    }
    return data_type_mapping.get(pandas_dtype, 'TEXT')


def sanitize_name(name):
    sanitized_name = ''.join(c if c.isalnum() else '_' for c in name)
    sanitized_name = sanitized_name.strip('_').lower()
    if sanitized_name[0].isdigit():
        sanitized_name = "col_" + sanitized_name
    max_name_length = 64
    if len(sanitized_name) > max_name_length:
        sanitized_name = sanitized_name[:max_name_length]
    return sanitized_name


@app.route('/migrate', methods=['GET', 'POST'])
def migrate():
    if request.method == 'POST':
        db_name = request.form['db_name']
        if not is_valid_db_name(db_name):
            flash("Invalid database name. Please provide a valid name.", "error")
        elif db_exists(db_name):
            flash("Database already exists. Please choose a different name.", "error")
        else:
            excel_file = request.files['excel_file']
            if excel_file.filename == '':
                flash("No Excel file selected. Please select an Excel file.", "error")
            elif not excel_file.filename.endswith('.xlsx'):
                flash("Incorrect file extension. Please select an Excel file with .xlsx or .csv extension.", "error")
            else:
                db_config = {
                    "host": "localhost",
                    "user": "root",
                    "password": "admin",
                    "database": db_name,
                    "port": 3306
                }
                try:
                    create_database(db_name)
                    excel_to_database(excel_file, db_config)
                except Exception as e:
                    flash(f"Migration failed: {str(e)}", "error")
                else:
                    flash("Migration successful!", "success")

    return render_template('migrate.html')



def excel_to_database(excel_file, db_config):
    db_conn = None
    cursor = None
    try:
        db_conn = mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        flash(f"Failed to connect to the database: {str(err)}", "error")
        return
    try:
        cursor = db_conn.cursor()

        excel_data = pd.read_excel(excel_file, sheet_name=None)

        for sheet_name, sheet_df in excel_data.items():
            table_name = sanitize_name(sheet_name)

            create_table_query = f"CREATE TABLE IF NOT EXISTS `{table_name}` ("
            column_definitions = []

            for column_name in sheet_df.columns:
                sanitized_column_name = sanitize_name(column_name)
                pandas_data_type = sheet_df[column_name].dtype
                mysql_data_type = get_mysql_data_type(pandas_data_type)
                column_definitions.append(f"`{sanitized_column_name}` {mysql_data_type}")

            create_table_query += ', '.join(column_definitions) + ");"
            cursor.execute(create_table_query)

            columns = ', '.join([f"`{sanitize_name(col)}`" for col in sheet_df.columns])
            insert_query = f"INSERT INTO `{table_name}` ({columns}) VALUES ({', '.join(['%s'] * len(sheet_df.columns))})"

            for _, row in sheet_df.iterrows():
                values = []
                for value in row:
                    if pd.notna(value):
                        if value == '√':
                            values.append('yes')
                        else:
                            values.append(str(value))
                    else:
                        values.append(None)

                cursor.execute(insert_query, tuple(values))

        db_conn.commit()
    except mysql.connector.Error as err:
        flash(f"Migration failed: {str(err)}", "error")
    finally:
        if cursor:
            cursor.close()
        if db_conn:
            db_conn.close()


def db_exists(db_name):
    db_conn = mysql.connector.connect(**db_config)
    cursor = db_conn.cursor()
    cursor.execute("SHOW DATABASES;")
    databases = [row[0] for row in cursor.fetchall()]
    db_conn.close()

    return db_name in databases


def is_valid_db_name(db_name):
    # Check if the name is not empty
    if not db_name:
        return False
    
    # Check if the name consists of only alphanumeric characters and underscores
    # if not db_name.isalnum() or '_' in db_name:
    #     return False
    
    # Check if the name starts with a letter
    if not db_name[0].isalpha():
        return False
    
    # Check if the name is not a reserved keyword (modify the list as needed)
    reserved_keywords = ['mysql', 'information_schema', 'performance_schema']
    if db_name.lower() in reserved_keywords:
        return False
    
    # Check if the name is not too long (adjust the maximum length as needed)
    max_name_length = 64
    if len(db_name) > max_name_length:
        return False
    
    return True


@app.route('/show_databases')
def show_databases():
    db_conn = mysql.connector.connect(**db_config)
    cursor = db_conn.cursor()
    cursor.execute("SHOW DATABASES;")
    databases = [row[0] for row in cursor.fetchall()]
    db_conn.close()

    return render_template('show_databases.html', databases=databases)

@app.route('/show_tables/<db_name>')
def show_tables(db_name):
    if db_exists(db_name):
        db_conn = mysql.connector.connect(**db_config, database=db_name)
        cursor = db_conn.cursor()
        cursor.execute(f"SHOW TABLES;")
        tables = [row[0] for row in cursor.fetchall()]
        db_conn.close()

        return render_template('show_tables.html', db_name=db_name, tables=tables)



@app.route('/show_table_data/<db_name>/<table_name>', methods=['GET'])
def show_table_data(db_name, table_name):
    if db_exists(db_name):

        db_conn = mysql.connector.connect(**db_config, database=db_name)
        cursor = db_conn.cursor()

        search_term = request.args.get('search')
        if search_term:
            search_query = f"SELECT * FROM `{table_name}` WHERE "
            search_query += ' OR '.join([f"`{col}` LIKE %s" for col in columns])
            cursor.execute(search_query, ['%' + search_term + '%'] * len(columns))
            table_data = cursor.fetchall()
        else:
            cursor.execute(f"SELECT * FROM `{table_name}`")
            table_data = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        db_conn.close()

        if request.headers.get('Accept') == 'application/json':
            # If the request wants JSON data (such as from DataTables), return JSON
            data = []
            for row in table_data:
                data.append(dict(zip(columns, row)))
            return jsonify(data)
        else:
            # If the request wants HTML data (such as from the HTML-based page), return HTML
            return render_template('datatables.html', **db_config, table_data=table_data)
    
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


# Function to fetch all records from a table
def fetch_all_records():
    try:
        db_conn = mysql.connector.connect(**db_config)
        cursor = db_conn.cursor()

        # Get a list of all databases
        cursor.execute("SHOW DATABASES;")
        databases = [row[0] for row in cursor.fetchall()]

        # Create a dictionary to store records for each database
        all_records = {}

        for db in databases:
            cursor.execute(f"USE `{db}`;")  # Switch to the current database
            cursor.execute("SHOW TABLES;")
            tables = [row[0] for row in cursor.fetchall()]

            records = []

            # Fetch records from each table in the current database
            for table in tables:
                cursor.execute(f"SELECT * FROM `{table}`;")
                table_records = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                # Convert records to dictionaries for easier handling
                table_records = [dict(zip(columns, record)) for record in table_records]
                
                records.extend(table_records)

            all_records[db] = records

        db_conn.close()
        return all_records
    except Exception as e:
        print(f"Error fetching records: {str(e)}")
        return {}
    
class DatabaseNotFoundError(Exception):
    pass


class DatabaseConnectionError(Exception):
    pass

# Set up logging
logging.basicConfig(filename='search_application.log', level=logging.ERROR)

# Function to perform a search based on user query
# def perform_search(query, selected_database):
#     try:
#         records = fetch_all_records()  # Fetch all records from the database

#         if selected_database in records:
#             records = records[selected_database]
#         else:
#             # Raise a custom exception when the selected database is not found
#             raise DatabaseNotFoundError("Selected database not found in the list")

#         # Tokenize and process the user's query
#         keywords = [keyword.lower() for keyword in query.split()]

#         results = []
#         for record in records:
#             # Iterate through all values in the record
#             for key, value in record.items():
#                 # Stem the value for comparison
#                 stemmed_value = stem_keyword(str(value).lower())
#                 # Check if any stemmed keyword is in the stemmed value
#                 if any(keyword in stemmed_value for keyword in keywords):
#                     results.append(record)
#                     break  # Stop searching this record if a match is found

#         return results

#     except DatabaseConnectionError as e:
#         # Handle the database connection error (e.g., log it or return an error message)
#         logging.error(f"Database connection error: {str(e)}")
#         return []
#     except DatabaseNotFoundError as e:
#         # Handle the case where the selected database is not found
#         logging.error(f"Selected database not found: {str(e)}")
#         return []
#     except Exception as e:
#         # Handle other unexpected exceptions (e.g., log them or return an error message)
#         logging.error(f"An unexpected error occurred: {str(e)}")
#         return []

def perform_search(query, selected_database):
    try:
        records = fetch_all_records()  # Fetch all records from the database

        if selected_database in records:
            records = records[selected_database]
        else:
            # Raise a custom exception when the selected database is not found
            raise DatabaseNotFoundError("Selected database not found in the list")

        # Preprocess and tokenize the user's query
        query = query.lower()  # Convert query to lowercase
        keywords = query.split()  # Tokenize query

        # Prepare the text data for records
        record_texts = [" ".join(str(value) for value in record.values()) for record in records]

        # Initialize TF-IDF vectorizer
        tfidf_vectorizer = TfidfVectorizer()

        # Fit and transform the vectorizer on the record texts
        tfidf_matrix = tfidf_vectorizer.fit_transform(record_texts)

        # Transform the query using the same vectorizer
        query_vector = tfidf_vectorizer.transform([query])

        # Compute cosine similarity between the query and records
        cosine_similarities = linear_kernel(query_vector, tfidf_matrix).flatten()

        # Sort results by similarity
        results = [record for record, score in zip(records, cosine_similarities) if score > 0.0]
        results.sort(key=lambda x: -cosine_similarities[records.index(x)])

        #print(f"Results {results}")

        return results
    except Exception as e:
        print(f"Error performing TF-IDF search: {str(e)}")
        return []

# You can now call perform_search with your query
#search_results = perform_search("your search query", "selected_database")

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        selected_database = request.form.get('selected_database')
        query = request.form.get('query')

        if selected_database and query:
            try:
                results = perform_search(query, selected_database)
                return render_template('search_application.html', results=results)
            except DatabaseNotFoundError:
                return jsonify(error='Selected database not found in the list'), 404

    # Return an empty result for the initial page load or if no valid search parameters are provided
    return render_template('search_application.html', results=[])




if __name__ == '__main__':
    app.run(debug=True)