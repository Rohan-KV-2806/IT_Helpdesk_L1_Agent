import joblib

MODEL_PATH = "ClassifierModels/ProblemClassifier.joblib"

# Load trained model and TF-IDF vectorizer
saved_model = joblib.load(MODEL_PATH)

vectorizer = saved_model["vectorizer"]
model = saved_model["model"]

print("Classifier loaded successfully.")
print("Type 'exit' to quit.\n")

while True:
    query = input("Enter your IT problem: ")

    if query.lower() == "exit":
        break

    # Convert user query into TF-IDF
    query_tfidf = vectorizer.transform([query])

    # Predict intent
    prediction = model.predict(query_tfidf)[0]

    print(f"Intent: {prediction}\n")