import bcrypt

senha = b"user"  
hash = bcrypt.hashpw(senha, bcrypt.gensalt()).decode()
print(hash)