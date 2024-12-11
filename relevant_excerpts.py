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
        #cache_embeddings(embeddings, text_chunks, pdf_path, path_fxn)
        return embeddings, text_chunks

def embed_schema_col(openai_client, prompt):
    return generate_embedding(openai_client, prompt)

def embed_schema(openai_client, schema):
    col_embeddings = {}
    for col in schema:
        prompt = col
        spec_dict = {"column_description": "", "context": ""}
        if "column_description" in schema[col]:
            col_desc = schema[col]["column_description"]
            if len(col_desc)>1:
                prompt = f"{col}: '{col_desc}'"
                spec_dict["column_description"] = col_desc
        if 'context' in schema[col]:
            context = schema[col]["context"]
            if len(context) > 1:
                prompt += f". Context: {context}"
                spec_dict["context"] = context
        spec_dict['embedding'] = embed_schema_col(openai_client, prompt)
        col_embeddings[col] = spec_dict
    return col_embeddings

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_top_relevant_texts(text_embeddings, pdf_text_chunks, col_embedding, num_excerpts, var_name):
    relevant_texts = []
    indeces = set()
    similarity_scores = []
    for i in range(len(text_embeddings)):
        if var_name in pdf_text_chunks[i]:
            indeces.add(i)
            relevant_texts.append((text_embeddings[i], pdf_text_chunks[i]))
        text_embedding = text_embeddings[i]
        similarity = cosine_similarity(col_embedding, text_embedding)
        similarity_scores.append((i, similarity))
    # Sort by similarity score in descending order and take the top_n items
    sorted_embeddings = sorted(similarity_scores, key=lambda x: x[1], reverse=True)[:num_excerpts]
    ## RETURNS [(textembed, text), ..., 10x] for each column
    return relevant_texts + [(text_embeddings[i], pdf_text_chunks[i]) for i, _ in sorted_embeddings if i not in indeces]
