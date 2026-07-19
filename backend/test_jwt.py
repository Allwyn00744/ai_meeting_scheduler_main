from app.auth.jwt_handler import create_access_token, verify_access_token

token = create_access_token(
    {
        "user_id": 1,
        "email": "allwyn@gmail.com"
    }
)

print("Token:\n")
print(token)

print("\nDecoded:\n")
print(verify_access_token(token))