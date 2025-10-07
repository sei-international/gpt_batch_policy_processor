import json
import numpy as np
import os
import tiktoken


def get_cache_fname(pdf_path, path_fxn):
    pdf_fname = os.path.basename(pdf_path)
    cache_dir = path_fxn("embeddings_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    return f"{cache_dir}/{pdf_fname.replace('.pdf','.json')}"


def cache_embeddings(text_chunks, pdf_file_path, path_fxn):
    json_file_path = get_cache_fname(pdf_file_path, path_fxn)
    output_dict = {"text_chunks_w_embeddings": text_chunks}
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(output_dict, f)


def generate_embeddings(openai_client, text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(model=model, input=text)
    return response


def generate_embedding(openai_client, text):
    r = generate_embeddings(openai_client, text)
    return r.data[0].embedding


def generate_all_embeddings(openai_client, pdf_path, text_chunks, path_fxn):
    embeddings_model, token_limit = "text-embedding-3-small", 6000
    cache_fname = get_cache_fname(pdf_path, path_fxn)
    if os.path.exists(cache_fname):
        with open(cache_fname, "r", encoding="utf-8") as f:
            cached_embeddings = json.load(f)
            return cached_embeddings["text_chunks_w_embeddings"]
    else:
        batches = []
        current_batch = []
        current_tokens = 0
        enc = tiktoken.encoding_for_model(embeddings_model)
        for text_chunk_dict in text_chunks:
            text = text_chunk_dict["text_chunk"]
            tokens = len(enc.encode(text))
            if current_tokens + tokens > token_limit:
                batches.append(current_batch)
                current_batch = [text]
                current_tokens = tokens
            else:
                current_batch.append(text)
                current_tokens += tokens
        if len(current_batch) > 0:
            batches.append(current_batch)

        embeddings = []
        for batch in batches:
            try:
                response = generate_embeddings(openai_client, batch, embeddings_model)
                embeddings.extend([r.embedding for r in response.data])
            except Exception as e:
                try:
                    for text in batch:
                        response = generate_embedding(openai_client, text)
                        embeddings.append(response)
                except Exception as e2:
                    print(f"Error generating embeddings for batch: {e}, {e2}")

        for i in range(len(text_chunks)):
            text_chunks[i]["embedding"] = embeddings[i]
        cache_embeddings(text_chunks, pdf_path, path_fxn)
        return text_chunks


def embed_one_variable_specification(openai_client, prompt):
    return generate_embedding(openai_client, prompt)


def embed_variable_specifications(openai_client, variables):
    var_embeddings = {}
    for var in variables:
        prompt = var
        spec_dict = {"variable_description": "", "context": ""}
        if "variable_description" in variables[var]:
            var_desc = variables[var]["variable_description"]
            if len(var_desc) > 1:
                prompt = f"{var}: '{var_desc}'"
                spec_dict["variable_description"] = var_desc
        if "context" in variables[var]:
            context = variables[var]["context"]
            if len(context) > 1:
                prompt += f". Context: {context}"
                spec_dict["context"] = context
        spec_dict["embedding"] = embed_one_variable_specification(openai_client, prompt)
        var_embeddings[var] = spec_dict
    return var_embeddings


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def find_top_relevant_texts(
    pdf_text_chunks_w_embeddings, var_embedding, min_num_excerpts, var_name, gpt_model
):
    if not pdf_text_chunks_w_embeddings:
        return []
    
    max_tokens_per_model = {
        "gpt-4.1": 1047576,
        "gpt-5": 400000,
        "gpt-4o": 128000,
        "o4-mini": 200000,
        "o3": 200000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-3.5-turbo": 16385,
    }  
    max_chars_total = max_tokens_per_model[gpt_model]  * 4
    max_chars_for_excerpts = max_chars_total - 20000
    relevant_texts = []
    indeces = set()
    similarity_scores = []
    total_excerpt_num_chars = 0
    for i in range(len(pdf_text_chunks_w_embeddings)):
        text_chunk_dict = pdf_text_chunks_w_embeddings[i]
        txt, txt_embs = [text_chunk_dict[k] for k in ["text_chunk", "embedding"]]
        if var_name in txt:
            indeces.add(i)
            relevant_texts.append(text_chunk_dict)
            total_excerpt_num_chars +=len(text_chunk_dict["text_chunk"])
        similarity = cosine_similarity(var_embedding, txt_embs)
        similarity_scores.append((i, similarity))
    sorted_embeddings = sorted(similarity_scores, key=lambda x: x[1], reverse=True)
    for sim_score in sorted_embeddings:
        i = sim_score[0]
        if i not in indeces:
            if sim_score[1] > 0.7:
                relevant_texts.append(pdf_text_chunks_w_embeddings[i])
                indeces.add(i)
                total_excerpt_num_chars += len(pdf_text_chunks_w_embeddings[i]["text_chunk"])
                if total_excerpt_num_chars > max_chars_for_excerpts:
                    return relevant_texts
    if len(relevant_texts) < min_num_excerpts:
        j=0
        max_j = len(sorted_embeddings)
        while len(relevant_texts) < min_num_excerpts and j < max_j:
            emb_i = sorted_embeddings[j][0]
            if emb_i not in indeces:
                relevant_texts.append(pdf_text_chunks_w_embeddings[emb_i])
                indeces.add(emb_i)
            j+=1
    return relevant_texts
