from openai import OpenAI

client = OpenAI(api_key="sk-rslLztN0IfYSOZUlLcDUxSLf8M8yGMHz", base_url="https://api.proxyapi.ru/openai/v1")

def neiro(message, model, sisprompt):
    
    promt = sisprompt + message 
    completion = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[ {"role": "user", "content": promt}] 
    )
    text = completion.choices[0].message.content
    return text

    
    






















































#{"role": "system", "content": sistpromt},
