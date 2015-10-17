# -*- coding: utf-8 -*-
"""
Created on Sat Oct 17 06:56:54 2015

@author: wcramblit
"""

###### ADD API KEY BELOW

KEY = ''

##### ADD API KEY ABOVE

import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
import itertools
import sqlite3 as lite
import sklearn.cluster as cluster


def pull_demo_data(state,city,neighborhood): # Pulls data from Zillow API, returns Element Tree Root
    key = KEY
    state = state
    city = city
    neighborhood = neighborhood
    path = ("http://www.zillow.com/webservice/GetDemographics.htm?zws-id=" + str(key) + "&state=" + str(state) + "&city=" + str(city) + "&neighborhood=" + str(neighborhood))
    # API pull
    resp = requests.get(path)
    text = resp.content
    root = ET.fromstring(text)
    return root

def hood_list(state,city): # creates list of available neighborhoods from Zillow API
    key = KEY
    path = ("http://www.zillow.com/webservice/GetRegionChildren.htm?zws-id=" + str(key) + "&state=" + str(state) + "&city=" + str(city) + "&childtype=neighborhood")
    resp = requests.get(path)
    text = resp.content
    hood_root = ET.fromstring(text)
    hood_list = [i.find('name').text for i in hood_root.find('response').find('list').iter('region') if hood_root.find('response') is not None]
    return hood_list

def fields_generator(state,city,hood_list): # generates dictionary of neighborhoods with their roots
    # pulls each neighborhood's export "root" and stores in a nifty dictionary with key as hood name, root as value
    city_dict = {}
    fields_raw = []
    for hood in hood_list:
        root = pull_demo_data(state,city,hood)
        city_dict[hood] = root #adds the neighborhood and corresponding root to a dictionary
    return city_dict

def city_dataframe(hood_list,root_dict,db,city):
    # pulls data from root, creates df, saves df with name of city to database
    city_value_dictionary = {}
    for hood in hood_list:
        temp_dictionary = {}
        root = root_dict[hood]
        for i in root.find('response').find('pages').iter('attribute'):
            values = i.find('values')
            name = i.find('name').text
            if values is not None:
                neigh = values.find('neighborhood')
                if neigh is not None:
                    neigh = neigh.find('value').text
                else:
                    neigh = neigh
            else:
                neigh = np.nan
            temp_dictionary[name] = neigh
        city_value_dictionary[hood] = temp_dictionary
    d = pd.DataFrame(city_value_dictionary)
    d.fillna(value=np.nan,inplace=True)
    cols = d.columns
    cols = cols.map(lambda x: x.replace(' ', '_').replace('.', '') if isinstance(x, (str, unicode)) else x)
    d.columns = cols
    d.index = [i.replace('.','') for i in d.index]
    d.index = [i.replace(' ','_') for i in d.index]
    con = lite.connect(db)
    city_rev = city.replace(' ','_')
    d.to_sql(str(city_rev),con,if_exists='replace')

def initiator_single(): # runs to begin the program, manages order of events to limit API double dips
    city1 = raw_input("Enter origin city: ") # user defines origin and destination city and state
    state1 = raw_input("Enter origin state (two-letter abbreviation): ")
    city2 = raw_input("Enter destination city: ")
    state2 = raw_input("Enter destination state (two-letter abbreviation): ")
    city_rev1 = city1.replace(' ','_')
    city_rev2 = city2.replace(' ','_')
    db = 'all_city_data.db'
    con = lite.connect(db)
    with con:
        # check if table already exists for city 1 and city 2
        cur = con.cursor()
        cur.execute(""" SELECT COUNT(*) FROM sqlite_master WHERE name = ?  """, (city_rev1, ))
        result1 = cur.fetchone()
        cur.execute(""" SELECT COUNT(*) FROM sqlite_master WHERE name = ?  """, (city_rev2, ))
        result2 = cur.fetchone()
        if sum(result1) > 0 and sum(result2) > 0: #if there's a table, extract the data from the db as db1
            d_final = db_extract_single(db,city1,city2)
            cluster_fields = d_final.columns.values # this will return as an array of cluster variables
        elif sum(result1) <= 0 and sum(result2) > 0:
            # if city 1 doesn't exist in db, pulls data into db then uses city dataframe to extract
            hood_list1 = hood_list(state1,city1)
            city_dict1 = fields_generator(state1,city1,hood_list1)
            city_dataframe(hood_list1,city_dict1,db,city1)
            d_final = db_extract_single(db,city1,city2)
            cluster_fields = d_final.columns.values # this will return as an array of cluster variables
        elif sum(result1) >0 and sum(result2) <= 0: #if city two doesnt exist yet...
            hood_list2 = hood_list(state2,city2)
            city_dict2 = fields_generator(state2,city2,hood_list2)
            city_dataframe(hood_list2,city_dict2,db,city2)
            d_final = db_extract_single(db,city1,city2)
            cluster_fields = d_final.columns.values # this will return as an array of cluster variables
        else: #otherwise, pull both from API
            hood_list1 = hood_list(state1,city1)
            city_dict1 = fields_generator(state1,city1,hood_list1)
            city_dataframe(hood_list1,city_dict1,db,city1)
            hood_list2 = hood_list(state2,city2)
            city_dict2 = fields_generator(state2,city2,hood_list2)
            city_dataframe(hood_list2,city_dict2,db,city2)
            d_final = db_extract_single(db,city1,city2)
            cluster_fields = d_final.columns.values # this will return as an array of cluster variables
        return kmeans_model_single(d_final), cluster_fields
    con.close()

def db_extract_single(db,city1,city2):
    con = lite.connect(db)
    city_rev_1 = city1.replace(' ','_')
    city_rev_2 = city2.replace(' ','_')
    with con:
        #pull city1
        cur = con.cursor()
        cur.execute('SELECT * FROM ' + str(city_rev_1))
        rows_1 = cur.fetchall()
        cols_1 = [desc[0] for desc in cur.description]
        new_df_1 = pd.DataFrame(rows_1,columns=cols_1)
        new_df_1.set_index('index', inplace=True)
        new_df_1.index.name = None #gets rid of index name, which was populating a blank row
        new_df_1.columns = new_df_1.columns.map(lambda x: str(x) + '-' + str(city1))
        #pull city2
        cur = con.cursor()
        cur.execute('SELECT * FROM ' + str(city_rev_2))
        rows_2 = cur.fetchall()
        cols_2 = [desc[0] for desc in cur.description]
        new_df_2 = pd.DataFrame(rows_2,columns=cols_2)
        new_df_2.set_index('index', inplace=True)
        new_df_2.index.name = None #gets rid of index name, which was populating a blank row
        new_df_2.columns = new_df_2.columns.map(lambda x: str(x) + '-' + str(city2))
    con.close()
    new_df_1 = new_df_1.transpose()
    new_df_2 = new_df_2.transpose()
    frames = [new_df_1,new_df_2]
    new_df = pd.concat(frames, join='outer')
    for i in new_df:
        column_score = sum(value is None or value == "0" or value == 0 for value in new_df[i])
        if column_score/float(len(new_df)) >= 0.5:
            del new_df[i]
    useless_hoods = [row[0] for row in new_df.itertuples() if sum(value is None or value == '0' or value == 0 for value in row)/float(len(row)) >= 0.80]
    new_df = new_df.drop(useless_hoods)
    new_df.dropna(axis='index',how='any',inplace=True)
    return new_df

def kmeans_model_single(city_df): 
    km = cluster.KMeans(n_clusters=int(len(city_df)/4))
    model = km.fit(city_df)
    cluster_dict = dict(zip(city_df.index, model.predict(city_df)))
    cluster_df = pd.DataFrame.from_dict(cluster_dict,orient='index')
    result = cluster_df.sort(columns=0)
    return result
    

result, fields  = initiator_single()
print fields
print result