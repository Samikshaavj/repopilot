import numpy as np
from sentence_transformers import SentenceTransformer

# Downloads the model the first time (~130 MB), then reuses it
model = SentenceTransformer("BAAI/bge-small-en-v1.5")

texts = [
    "def login(user, password): check the password and start a session",
    "def authenticate(credentials): verify credentials and create a login session",
    "def resize_image(img, width, height): scale an image to a new size",
]

vectors = model.encode(texts, normalize_embeddings=True)

print("shape:", vectors.shape)
print("first 5 numbers of text 1:", vectors[0][:5])

print("\nlogin vs authenticate:", round(float(np.dot(vectors[0], vectors[1])), 3))
print("login vs resize_image:", round(float(np.dot(vectors[0], vectors[2])), 3))

# A search query, the way the app will use it
query = "Represent this sentence for searching relevant passages: where is user authentication handled?"
query_vector = model.encode(query, normalize_embeddings=True)

print("\nquery similarity to each text:")
for text, vector in zip(texts, vectors):
    print(round(float(np.dot(query_vector, vector)), 3), text[:45])