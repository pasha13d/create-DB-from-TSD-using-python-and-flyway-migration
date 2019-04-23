#!/usr/bin/env python3

import json
import os
import shutil
import sys
import time

import gspread
from gspread import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials


class SqlScriptGenerator(object):

    _CREDENTIAL = '../config/credential.json'
    _GOOGLE_SHEET_NAME = 'CSSM__Table-State-Data'
    _SHEET_TAB_NAME = 'schema'

    def __init__(self):
        self.start_time = int(round(time.time() * 1000))

    def load_script(self, json_file_name):
        g_sheet = self.g.open(self._GOOGLE_SHEET_NAME)
        range = g_sheet.worksheet(self._SHEET_TAB_NAME).get_all_values()
        dict = {}
        for row in range[3:]:
            dir_name = row[4] + '-' + row[5]
            if dir_name not in dict:
                dict[dir_name] = []

            # Script
            scripts = dict[dir_name]
            script = {}
            script_name = row[4] + '_' + row[6] + '__' + row[7] + '.sql'
            idx_script = self.find_index(scripts, 'script', script_name)
            if idx_script == -1:
                script['script'] = script_name
                script['tables'] = []
                scripts.append(script)
            else:
                script = scripts[idx_script]

            # Table
            tables = script['tables']
            table = {}
            idx_table = self.find_index(tables, 'tableName', row[8])
            if idx_table == -1:
                table['tableName'] = row[8]
                table['sortOrder'] = int(row[2])
                table['columns'] = []
                table['constraints'] = []
                table['data'] = []

                if row[3] == '0' and row[9] == '-':
                    table['partition'] = row[18]
                else:
                    table['partition'] = ''

                if row[3] == '0' and row[9] == '-':
                    table['notes'] = row[19]
                else:
                    table['notes'] = ''
                tables.append(table)
            else:
                table = tables[idx_table]

            # Column
            if row[3] != '0' and row[9] != '-':
                columns = table['columns']
                column = {}
                column['sortOrder'] = int(row[3])
                column['columnName'] = row[9]
                column['type'] = row[10]
                column['precision'] = row[11]
                column['scale'] = row[12]
                column['required'] = row[13]
                column['default'] = row[14]
                column['partition'] = row[18]
                column['notes'] = row[19]
                columns.append(column)

            # Constraint
            if row[3] != '-' and row[15] != '-':
                constraints = table['constraints']
                constraint = {}
                constraint['columnName'] = row[9]
                constraint['constraintType'] = row[15]
                constraint['check'] = row[16]
                constraint['reference'] = row[17]
                constraint['sortOrder'] = int(row[3])
                constraints.append(constraint)

            dict[dir_name] = scripts
        # End

        for dir_name, scripts in dict.items():
            for s, script in enumerate(scripts):
                tables = script['tables']
                for t, table in enumerate(tables):
                    try:
                        worksheet = g_sheet.worksheet(table['tableName'])
                        table['data'] = worksheet.get_all_values()
                    except WorksheetNotFound:
                        pass  # already exists

        with open(json_file_name, 'w') as jsonFile:
            print(json.dumps(dict, indent=4), file=jsonFile)

        # print('1. Download time in :', int(round(time.time() * 1000)) - self.start_time, 'ms')

    def generate_data(self, table, range):
        insert_sql = '-- ' + table['tableName'] + '\n'
        cols = range[0]
        for row in range[1:]:
            insert_sql += 'insert into ' + table['tableName'] + ' (' + ', '.join(cols) + ') values ('
            insert_sql += self.generate_value(table, cols, row)
            insert_sql += ');\n'
        insert_sql += 'commit;\n\n'
        return insert_sql

    def generate_value(self, table, cols, row):
        values = ''
        for c, col in enumerate(cols):
            idx_column = self.find_index(table['columns'], 'columnName', col)
            if idx_column == -1:
                continue
            column = table['columns'][idx_column]
            if column['type'] is 'numeric':
                values += row[c] + ','
            else:
                if row[c]:
                    values += '\'' + row[c] + '\','
                else:
                    values += 'null,'
        return values[:-1]

    def generate_script(self, deployment_type, json_file_name):
        self.start_time = int(round(time.time() * 1000))

        with open(json_file_name, 'r') as data_file:
            dict = json.loads(data_file.read())

        for dir_name, scripts in dict.items():
            for s, script in enumerate(scripts):
                sql_table_script = ''
                sql_insert_script = ''

                script['tables'].sort(key=lambda x: x['sortOrder'], reverse=False)
                tables = script['tables']

                for t, table in enumerate(tables):
                    partition_column = None
                    table['columns'].sort(key=lambda x: x['sortOrder'], reverse=False)
                    columns = table['columns']

                    # Write Comment
                    sql_table_script += '/*\n' + table['notes'] + '\n'
                    for c, column in enumerate(columns):
                        sql_table_script += "{:40} : {}\n".format(column['columnName'], column['notes'])
                    sql_table_script += '*/\n'

                    # Write Table Script
                    sql_table_script += "{:40} {}\n".format('create table', table['tableName'])
                    sql_table_script += '(\n'
                    last_col_index = len(columns) - 1
                    for c, column in enumerate(columns):
                        if column['partition'].lower() == 'yes':
                            partition_column = column['columnName']

                        type = column['type']
                        if column['precision'] != '-':
                            if column['type'] == 'numeric':
                                if column['scale'] != '-':
                                    type += '(' + column['precision'] + ',' + column['scale'] + ')'
                                else:
                                    type += '(' + column['precision'] + ')'
                            elif column['type'] == 'varchar':
                                type += '(' + column['precision'] + ')'
                            else:
                                type += ''

                        required = ''
                        if column['required'] == 'Yes':
                            required = 'not null'

                        default = ''
                        if column['default'] != '-':
                            if column['default'] == 'current_user':
                                default = 'default ' + column['default']
                            elif column['type'] == 'varchar' or column['type'] == 'text':
                                default = 'default \'' + column['default'] + '\''
                            else:
                                default = 'default ' + column['default']

                        if default == '':
                            if required == '':
                                type_value = type
                            else:
                                type_value = "{:60}".format(type) + required
                        else:
                            type_value = "{:60}".format(type) + "{:15}".format(required) + default

                        if c == last_col_index:
                            if len(table['constraints']) > 0:
                                type_value += ','
                        else:
                            type_value += ','

                        sql_table_script += "{:40} {}\n".format(column['columnName'], type_value)

                    # Write Constraints
                    table['constraints'].sort(key=lambda x: x['sortOrder'], reverse=False)
                    constraints = table['constraints']
                    last_cons_index = len(constraints) - 1
                    for c, constraint in enumerate(constraints):
                        if constraint['constraintType'].lower() == 'Primary'.lower():
                            constraint_name = 'pk_' + table['tableName']
                            constraint_des = "{:14} {}".format('primary key', '(' + constraint['columnName'] + ')')
                        elif constraint['constraintType'].lower() == 'Foreign'.lower():
                            ref_values = constraint['reference'].split(".")
                            constraint_name = 'fk_' + constraint['columnName'] + '_' + table['tableName']
                            constraint_des = "{:14} {}".format('foreign key', '(' + constraint['columnName'] + ')\n')
                            constraint_des += "{:50} {:49} {:14} {}".format('', '', 'references', ref_values[0].strip() + '(' + ref_values[1].strip() + ')')
                            if len(ref_values) == 3:
                                constraint_des += "{:10} {}".format('', ref_values[2].strip())
                        elif constraint['constraintType'].lower() == 'Unique'.lower():
                            constraint_name = 'u_' + constraint['columnName'] + '_' + table['tableName']
                            constraint_des = "{:14} {}".format('unique', '(' + constraint['columnName'] + ')')
                        elif constraint['constraintType'].lower() == 'Check'.lower():
                            constraint_name = 'ck_' + constraint['columnName'] + '_' + table['tableName']
                            constraint_des = "{:14} {}".format('check', '(')
                            check_values = constraint['check'].split(",")
                            last_check_value = len(check_values) - 1
                            for c_idx, cv in enumerate(check_values):
                                constraint_des += constraint['columnName'] + ' = \'' + cv.strip() + '\''
                                if c_idx != last_check_value:
                                    constraint_des += ' or '
                            constraint_des += ')'

                        const_col = "{:40} {:60}{}".format('constraint', constraint_name, constraint_des)

                        if c != last_cons_index:
                            const_col += ','

                        sql_table_script += const_col + '\n'

                    # sql_table_script += ');\n\n'
                    if partition_column and deployment_type == 'prod':
                        sql_table_script = sql_table_script + ') partition by range (' + partition_column + ');\n\n'
                    else:
                        sql_table_script += ');\n\n'

                    if table['data'] and len(table['data']) > 0:
                        sql_insert_script += self.generate_data(table, table['data'])

                # Table Script
                file_name = 'R01_' + script['script']
                script_dir = os.path.dirname(os.path.abspath(__file__))
                dest_dir = os.path.join(script_dir, '01-table', dir_name)
                try:
                    os.makedirs(dest_dir)
                except OSError:
                    pass  # already exists
                path = os.path.join(dest_dir, file_name)
                with open(path, 'w') as sql_file:
                    print(sql_table_script, file=sql_file)

                # Insert Script
                if sql_insert_script:
                    file_name = 'R07_' + script['script']
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    dest_dir = os.path.join(script_dir, '07-insert', dir_name)
                    try:
                        os.makedirs(dest_dir)
                    except OSError:
                        pass  # already exists
                    path = os.path.join(dest_dir, file_name)
                    with open(path, 'w') as sql_file:
                        print(sql_insert_script, file=sql_file)

        # print('2. Sql file generation time in :', int(round(time.time() * 1000)) - self.start_time, 'ms')

    def find_index(self, list, property_name, property_value):
        for i, data in enumerate(list):
            if property_name in data and data[property_name] == property_value:
                return i
        return -1

    def validate_gsheet(self, rows):
        for row in rows:
            if not row['column'] or row['column'] is None or row['column'].strip() in ('', '-'):
                print('Column cannot contain empty', row['column'])
                return False
        return True

    def set_up(self):
        self.scope = ['https://spreadsheets.google.com/feeds']
        self.credentials = ServiceAccountCredentials.from_json_keyfile_name(self._CREDENTIAL, self.scope)
        self.g = gspread.authorize(self.credentials)

    def run(self, deployment_type='dev', json_file_name=None):
        if json_file_name is None:
            self.set_up()
            json_file_name = 'postgres.json'
            self.load_script(json_file_name)
        self.generate_script(deployment_type, json_file_name)


if __name__ == '__main__':
    generator = SqlScriptGenerator()
    if os.path.exists("./01-table"):
        shutil.rmtree('./01-table', ignore_errors=False, onerror=None)
    if os.path.exists("./07-insert"):
        shutil.rmtree('./07-insert', ignore_errors=False, onerror=None)
    os.mkdir('./01-table')
    os.mkdir('./07-insert')

    if len(sys.argv) == 3:
        if sys.argv[1] not in ('dev', 'prod'):
            print("Please enter proper deploy type as argument (dev/prod)")
            exit(1)
        generator.run(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        if sys.argv[1] not in ('dev', 'prod'):
            print("Please enter proper deploy type as argument (dev/prod)")
            exit(1)
        generator.run(sys.argv[1])
    else:
        print("Please enter deploy type as argument (dev/prod)")
        exit(1)
