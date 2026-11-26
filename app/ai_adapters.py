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

    def encode_texts(self,operation,texts,batch_size=32):
        if not texts:return []
        name=self.profile.query_prompt_name if operation=='query' else self.profile.document_prompt_name
        prefix=self.profile.query_prefix if operation=='query' else self.profile.document_prefix
        options={'prompt_name':name} if name else {'prompt':prefix}
        return self.model.encode(list(texts),batch_size=batch_size,normalize_embeddings=True,show_progress_bar=False,**options)

    def encode_image(self,image):
        raise ValueError('Unsupported image encoder')

    def encode_images(self,images,batch_size=4):
        raise ValueError('Unsupported image encoder')

    def encode_audio(self,window):
        raise ValueError('Unsupported audio encoder')

    def encode_video(self,window):
        raise ValueError('Unsupported video encoder')

class EmbeddingGemma2Adapter(SentenceTransformerAdapter):
    def config(self):
        config={} if 'audio' in self.profile.modalities else {'audio_config':None}
        if not {'cover','video'}.intersection(self.profile.modalities):
            config['vision_config']=None
        return config

    def encode_image(self,image):
        if 'cover' not in self.profile.modalities:
            raise ValueError('Unsupported image encoder')
        return self.model.encode({'image':image},normalize_embeddings=True)

    def encode_images(self,images,batch_size=4):
        if 'cover' not in self.profile.modalities:
            raise ValueError('Unsupported image encoder')
        if not images:return []
        return self.model.encode([{'image':image} for image in images],batch_size=batch_size,normalize_embeddings=True,show_progress_bar=False)

    def encode_audio(self,window):
        if 'audio' not in self.profile.modalities:raise ValueError('Unsupported audio encoder')
        from audio_input import validate_pcm
        import numpy as np
        validate_pcm(window)
        return self.model.encode({'audio':{'array':np.frombuffer(window.data,dtype='<f4'),'sampling_rate':window.sample_rate}},normalize_embeddings=True)

    def encode_video(self,window):
        if 'video' not in self.profile.modalities:raise ValueError('Unsupported video encoder')
        from PIL import Image
        from video_input import validate_video,MAX_FRAMES
        validate_video(window);frames=[]
        try:
            for data in window.frames:frames.append(Image.frombytes('RGB',(window.width,window.height),data))
            # Source timestamps remain interval evidence outside the embedding.
            # Already-sampled frames must not be sampled a second time by ST.
            return self.model.encode({'video':frames},normalize_embeddings=True,
                processing_kwargs={'video':{'do_sample_frames':False,'max_frames':MAX_FRAMES,
                                           'max_soft_tokens':140,'add_timestamps':False}})
        finally:
            for frame in frames:frame.close()

ADAPTERS={'embeddinggemma2':EmbeddingGemma2Adapter,'sentence-transformers':SentenceTransformerAdapter}

def load_adapter(profile,path,device,dtype):
    return ADAPTERS[profile.adapter](profile,path,device,dtype)
