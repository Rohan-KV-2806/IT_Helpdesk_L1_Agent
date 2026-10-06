import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
import joblib

df = pd.read_csv("data/helpdesk_intents_v2.csv")
print(df.head())
print(df.describe())
print(df.shape)
print(df.columns)
print(df["intent"].unique())

X = df["text"]
y = df["intent"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)
print("Training:", len(X_train))
print("Testing:", len(X_test))
print(y_train.value_counts())
print(y_train.value_counts())
vectorizer = TfidfVectorizer()

X_train_tfidf = vectorizer.fit_transform(X_train)
X_test_tfidf = vectorizer.transform(X_test)

model = LogisticRegression(max_iter=1000)
model.fit(X_train_tfidf, y_train)
y_pred = model.predict(X_test_tfidf)

print("Accuracy:", accuracy_score(y_test, y_pred))

messages = [
    "bro i literally cant open any website right now",                      # INTERNET_CONNECTIVITY
    "ping to the gateway works but everything outside times out",           # INTERNET_CONNECTIVITY
    "nslookup fails for our intranet but I can reach it by IP",             # DNS_PROBLEM
    "chrome keeps saying server not found for every site",                  # DNS_PROBLEM
    "my laptop keeps dropping off the wireless in the meeting room",        # WIFI_PROBLEM
    "can't see the office network in my list of available wifi",            # WIFI_PROBLEM
    "the vpn tunnel dies every time I open a big file from home",           # VPN_PROBLEM
    "anyconnect says login failed even though my password is right",        # VPN_PROBLEM
    "ipconfig shows 169.254 and nothing works",                             # IP_CONFIGURATION
    "I need to release and renew my ip lease",                              # IP_CONFIGURATION
    "ethernet adapter has vanished from device manager",                    # NETWORK_ADAPTER
    "can you disable and re-enable my network card?",                       # NETWORK_ADAPTER
    "my c drive is red and says almost full",                               # DISK_SPACE
    "how much free space do I have left on my laptop?",                     # DISK_SPACE
    "updates keep failing at 40 percent and then roll back",                # WINDOWS_UPDATE
    "pc has been stuck on working on updates for an hour",                  # WINDOWS_UPDATE
    "the windows time service wont start",                                  # WINDOWS_SERVICE
    "can you check if the bits service is running?",                        # WINDOWS_SERVICE
    "excel went white and says not responding",                             # APPLICATION_NOT_RESPONDING
    "sap just hangs when I click save, have to kill it",                    # APPLICATION_NOT_RESPONDING
    "task manager shows my processor pinned at 100 and the fan is screaming",  # HIGH_CPU_USAGE
    "what process is hogging my cpu?",                                      # HIGH_CPU_USAGE
    "windows says my computer is low on memory",                            # HIGH_MEMORY_USAGE
    "chrome is eating 7gb of ram",                                          # HIGH_MEMORY_USAGE
    "the printer says offline but its definitely on",                       # PRINTER_PROBLEM
    "outlook is stuck on loading profile",                                  # OUTLOOK_PROBLEM
    "I get access denied when I open the finance share",                    # FILE_FOLDER_PERMISSION
    "what windows version and build am I on?",                              # SYSTEM_INFORMATION
    "rdp to my office pc shows a black screen after login",                 # REMOTE_DESKTOP
    "what's a good recipe for dinner tonight?",                             # OTHER_UNKNOWN
]

messages_tfidf = vectorizer.transform(messages)

predictions = model.predict(messages_tfidf)

for message, prediction in zip(messages, predictions):
    print(f"{message} -> {prediction}")

joblib.dump(
    {
        "vectorizer": vectorizer,
        "model": model
    },
    "ClassifierModels/ProblemClassifier.joblib"
)

print("Model and vectorizer saved.")
print("model saved as ProblemClassifier.joblib")