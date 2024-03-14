import json
import numpy as np
import os

def get_cache_fname(pdf_path, path_fxn):
    pdf_fname = os.path.basename(pdf_path)
    cache_dir = path_fxn(f"embeddings_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    return f"{cache_dir}/{pdf_fname.replace('.pdf','.json')}"

def cache_embeddings(embeddings, text_chunks, pdf_file_path, path_fxn):
    json_file_path = get_cache_fname(pdf_file_path, path_fxn)
    output_dict = {"embeddings": embeddings, "text_chunks": text_chunks}
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(output_dict, f)

def generate_embedding(openai_client, text):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def generate_all_embeddings(openai_client, pdf_path, text_chunks, path_fxn):
    cache_fname = get_cache_fname(pdf_path, path_fxn)
    if os.path.exists(cache_fname):
        with open(cache_fname, "r", encoding="utf-8") as f:
            cached_embeddings = json.load(f)
            return cached_embeddings["embeddings"], cached_embeddings["text_chunks"]
    else:
        embeddings = [generate_embedding(openai_client, t) for t in text_chunks]
        cache_embeddings(embeddings, text_chunks, pdf_path, path_fxn)
        return embeddings, text_chunks

def embed_schema_col(openai_client, prompt):
    return generate_embedding(openai_client, prompt)

def embed_schema(openai_client, schema):
    col_embeddings = {}
    for col in schema:
        if col[:7] == "Section":
            section = schema[col]
            gen_prompt = section["general_prompt"]
            for subsection in section:
                if subsection != "general_prompt":
                    prompt = gen_prompt.replace("<var>", subsection)
                    if len(section[subsection])>0:
                      prompt = prompt + f"{subsection} includes {section[subsection]}. "
                    col_embeddings[subsection] = {"prompt": prompt, "embedding": embed_schema_col(openai_client, prompt)}
        elif col[:6] == "Select":
            select = schema[col]
            prompt = select["general_prompt"]
            options =  select["options"]
            i=1
            for option_name in options:
                prompt += f"Option{i}: {option_name}. "
                if len(options[option_name])>0:
                    prompt += f"{option_name} includes {options[option_name]}. "
                i=i+1
            col_embeddings[col] = {"prompt": prompt, "embedding": embed_schema_col(openai_client, prompt)}
        else:
            prompt = col
            if schema[col] != None:
                if len(schema[col])>1:
                    prompt = f"{col}: '{schema[col]}'"
            col_embeddings[col] = {"prompt": prompt, "embedding": embed_schema_col(openai_client, prompt)}
    return col_embeddings

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_top_relevant_texts(text_embeddings, pdf_text_chunks, col_embedding, top_n=20):
    similarity_scores = []
    for i in range(len(text_embeddings)):
        text_embedding = text_embeddings[i]
        similarity = cosine_similarity(col_embedding, text_embedding)
        similarity_scores.append((i, similarity))
    # Sort by similarity score in descending order and take the top_n items
    sorted_embeddings = sorted(similarity_scores, key=lambda x: x[1], reverse=True)[:top_n]
    ## RETURNS [(textembed, text), ..., 10x] for each column
    return [(text_embeddings[i], pdf_text_chunks[i]) for i, _ in sorted_embeddings]
