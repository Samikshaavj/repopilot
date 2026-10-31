import numpy as np
from fastembed import TextEmbedding
from sentence_transformers import SentenceTransformer

NAME = "BAAI/bge-small-en-v1.5"
TEXTS = [
    "def sign(self, value): sign a value and append the signature",
    "class BadSignature(BadData): raised if a signature does not match",
    "def derive_key(self, secret_key=None): derive the signing key from the secret key and salt",
    "how does token expiry work",
]

torch_vectors = SentenceTransformer(NAME).encode(TEXTS, normalize_embeddings=True)

onnx_vectors = np.array(list(TextEmbedding(model_name=NAME).embed(TEXTS)))
onnx_vectors = onnx_vectors / np.linalg.norm(onnx_vectors, axis=1, keepdims=True)

for text, a, b in zip(TEXTS, torch_vectors, onnx_vectors):
    print(f"similarity {float(np.dot(a, b)):.5f}   {text[:55]}")