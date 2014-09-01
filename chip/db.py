import os
import sqlite3

import util
import conf
cf = conf.read_conf()
join = os.path.join

db = sqlite3.connect(join(cf['home'], 'packages.db'))

def create_tables():
    c = db.cursor()
    c.execute("""create table pkgs (
        id integer primary key autoincrement not null, fullname text not null,
        name text not null, version text not null, author text, desc text,
        type text);"""
    )
    c.execute("""create table reqs (
        id int primary key not null, fullname text not null,
        name text not null, version text not null);"""
    )
    db.commit() 

def drop_tables():
    c = db.cursor()
    c.execute("drop table pkgs")
    c.execute("drop table reqs")
    db.commit()

def insert_package(pk):
    c = db.cursor()
    c.execute("""insert into pkgs(fullname, name, version, author, desc, type)
        values (?,?,?,?,?,?)""",  (util.format_pk_name(pk['name'], pk['version']),
            pk['name'], pk['version'], pk['author'], pk['desc'], pk['type']))
    db.commit()

def insert_all_packages():
    pks = util.getpk()
    for pk in pks:
        insert_package(pk)

def insert_req():
    pass
