# ******************************************************************************
# Copyright (c) 2020-2023, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

import base64
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import sqlite3

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


class ConnectorPasswords(object):
    rsa_private = '/etc/cloudblue-connector/connector.pem'
    passwords_db = '/etc/cloudblue-connector/passwords_db.sqlite3'

    def __init__(self):
        if not os.path.exists(self.rsa_private):
            self.generate_rsa_key()

        if not os.path.exists(self.passwords_db):
            self.create_database()

    def generate_rsa_key(self):
        if not os.path.exists(self.rsa_private):
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=default_backend()
            )
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            with open(self.rsa_private, 'wb') as f:
                f.write(private_pem)

    def create_database(self):
        conn = sqlite3.connect(self.passwords_db)
        cursor = conn.cursor()
        sql = """CREATE TABLE passwords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    service_name TEXT NOT NULL UNIQUE, 
                    service_password TEXT
                    );"""
        cursor.execute(sql)
        conn.close()

    def load_private_key(self):
        with open(self.rsa_private, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
            return private_key


    def encode_password(self, password):
        password = bytes(password, encoding='utf-8')
        private_key = self.load_private_key()
        public_key = private_key.public_key()

        encrypted = base64.b64encode(public_key.encrypt(
            password,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        ))

        return encrypted

    def decode_password(self, encrypted_password):
        private_key = self.load_private_key()
        decrypted = private_key.decrypt(
            base64.b64decode(encrypted_password),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted.decode(encoding='utf-8')

    def set_service_password(self, service, password):
        encrypted_password = self.encode_password(password)
        conn = sqlite3.connect(self.passwords_db)
        sql = 'INSERT OR REPLACE INTO passwords(service_name,service_password) VALUES(?,?)'
        cur = conn.cursor()
        cur.execute(sql, (service, encrypted_password))
        conn.commit()
        conn.close()

        return cur.lastrowid

    def get_service_password(self, service):
        conn = sqlite3.connect(self.passwords_db)
        cur = conn.cursor()
        cur.execute("SELECT service_password FROM passwords WHERE service_name=?", (service,))
        row = cur.fetchone()
        conn.close()
        return self.decode_password(row[0])

    @property
    def cloudblue_api_key(self):
        return self.get_service_password('cloudblue')

    @property
    def onnap_token(self):
        return self.get_service_password('onnap')

    @property
    def pp_password(self):
        return self.get_service_password('power_panel')
