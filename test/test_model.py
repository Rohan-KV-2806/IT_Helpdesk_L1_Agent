from llama_cpp import Llama

llm = Llama(
    model_path="models/Qwen_Qwen3-0.6B-Q4_K_M.gguf",
    n_ctx=3096,
    n_threads=2,
    verbose=False
)

prompt = """Classify this IT support request.

Choose exactly ONE category:
INTERNET
VPN
EMAIL
PRINTER
OTHER

Rules:
- Return ONLY the category name.
- Do not explain your answer.
- Do not repeat the user's message.
- Do not output punctuation.

User request:
"There seems to be a problem with my mail."
"""

response = llm.create_chat_completion(
    messages=[
        {
            "role": "system",
            "content": "You are an IT Helpdesk L1 classification agent. Follow the user's classification instructions exactly."
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.0,
    top_p=1.0,
    max_tokens=200
)

result = response["choices"][0]["message"]["content"].strip()

print("USER REQUEST")
print("There seems to be a problem with my email.")
print("\nAI RESPONSE")
print(result)