"""Small registered embedding backends. No dynamic plugin imports."""
class SentenceTransformerAdapter:
    def __init__(self,profile,path,device,dtype):
        from sentence_transformers import SentenceTransformer
        self.profile=profile
        self.model=SentenceTransformer(str(path),local_files_only=True,device=device,
            config_kwargs=self.config(),model_kwargs={'torch_dtype':dtype},trust_remote_code=False)
        self.dimension=self.model.get_embedding_dimension()
        if self.dimension!=profile.dimension:
            raise ValueError('Model dimension mismatch')

    def config(self):
        return {}

    def encode_text(self,operation,text):
        name=self.profile.query_prompt_name if operation=='query' else self.profile.document_prompt_name
        prefix=self.profile.query_prefix if operation=='query' else self.profile.document_prefix
        options={'prompt_name':name} if name else {'prompt':prefix}
        return self.model.encode(text,normalize_embeddings=True,**options)

    def encode_image(self,image):
        raise ValueError('Unsupported image encoder')

    def encode_audio(self,window):
        raise ValueError('Unsupported audio encoder')

class EmbeddingGemma2Adapter(SentenceTransformerAdapter):
    def config(self):
        config={} if 'audio' in self.profile.modalities else {'audio_config':None}
        if 'cover' not in self.profile.modalities:
            config['vision_config']=None
        return config

    def encode_image(self,image):
        if 'cover' not in self.profile.modalities:
            raise ValueError('Unsupported image encoder')
        return self.model.encode({'image':image},normalize_embeddings=True)

    def encode_audio(self,window):
        if 'audio' not in self.profile.modalities:raise ValueError('Unsupported audio encoder')
        from audio_input import validate_pcm
        import numpy as np
        validate_pcm(window)
        return self.model.encode({'audio':{'array':np.frombuffer(window.data,dtype='<f4'),'sampling_rate':window.sample_rate}},normalize_embeddings=True)

ADAPTERS={'embeddinggemma2':EmbeddingGemma2Adapter,'sentence-transformers':SentenceTransformerAdapter}

def load_adapter(profile,path,device,dtype):
    return ADAPTERS[profile.adapter](profile,path,device,dtype)
