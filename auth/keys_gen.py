from cryptography.fernet import Fernet
import secrets
# here you can generate a random JWT signing key and a Fernet key for encryption. 
# You can run this script and copy the output into your .env file.
jwt_key = secrets.token_urlsafe(32)

fernet_key = Fernet.generate_key().decode()

print("Copy this into your .env file:\n")
print(f"JWT_SIGNING_KEY={jwt_key}")
print(f"STORAGE_ENCRYPTION_KEY={fernet_key}")