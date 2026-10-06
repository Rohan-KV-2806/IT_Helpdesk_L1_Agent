from llama_cpp import Llama

llm = Llama(
    model_path="LocalLLMs/Qwen_Qwen3-0.6B-Q4_K_M.gguf",
    n_ctx=3096,
    n_threads=2,
    verbose=False
)

prompt = "HEy there seems to be a problem with my internt its not visible like dont have the option to connect internet"

response = llm.create_chat_completion(
    messages=[
        {
            "role": "system",
            "content": "You are an IT Helpdesk L1 agent. Understand the user's request and give a solution."
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