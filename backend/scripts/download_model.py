from app.embeddings import get_model

if __name__ == "__main__":
    vector = list(get_model().embed(["warm up"]))[0]
    print(f"Model ready: vectors have {len(vector)} numbers")