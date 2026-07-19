from app.auth.hashing import hash_password, verify_password

password = "12345678"

hashed = hash_password(password)

print("Original :", password)
print("Hashed   :", hashed)
print("Verified :", verify_password(password, hashed))