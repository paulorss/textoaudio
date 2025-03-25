import streamlit as st
import PyPDF2
import asyncio
from openai import AsyncOpenAI
import io

def main():
    st.title("Processador de PDF e Geração de Áudio")
    
    # Configuração da API Key
    st.header("Configuração da API OpenAI")
    api_key = st.text_input("Digite sua API Key da OpenAI", type="password")
    
    if api_key:
        # Configura a chave da API
        try:
            openai = AsyncOpenAI(api_key=api_key)
        except Exception as e:
            st.error(f"Erro ao configurar a API: {e}")
            return
        
        # Seção de upload de PDF
        st.header("Enviar PDF")
        uploaded_pdf = st.file_uploader("Escolha um arquivo PDF", type=['pdf'])
        
        # Seção de entrada de texto manual
        st.header("Ou Digite o Texto Manualmente")
        manual_text = st.text_area("Digite ou cole o texto aqui")
        
        # Configurações de voz
        st.header("Configurações de Voz")
        
        # Seleção de voz
        voice_options = [
            'alloy', 'ash', 'ballad', 'coral', 
            'echo', 'fable', 'onyx', 'nova', 
            'sage', 'shimmer'
        ]

        
        selected_voice = st.selectbox("Escolha a Voz", voice_options, index=3)  # Padrão 'coral'
        
        # Opções de formato de áudio
        audio_formats = ['mp3', 'opus', 'wav', 'aac', 'flac', 'pcm']
        selected_format = st.selectbox("Escolha o Formato de Áudio", audio_formats, index=0)
        
                      
        def extract_text_from_pdf(uploaded_file):
            """
            Extrai texto de um arquivo PDF carregado.
            """
            try:
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
            except Exception as e:
                st.error(f"Erro ao extrair texto do PDF: {e}")
                return None

        async def generate_audio(input_text, voice, audio_format):
            """
            Gera áudio a partir do texto de entrada usando a API da OpenAI.
            """
            try:
                async with openai.audio.speech.with_streaming_response.create(
                    model="gpt-4o-mini-tts",
                    voice=voice,
                    input=input_text,
                    response_format=audio_format
                ) as response:
                    audio_data = await response.read()
                return audio_data
            except Exception as e:
                st.error(f"Erro ao gerar áudio: {e}")
                return None
        
        # Aviso de divulgação
        st.warning("⚠️ Lembre-se: É necessário informar aos usuários finais que o áudio é gerado por IA.")
        
        # Botão de processamento
        if st.button("Gerar Áudio"):
            # Prioriza texto do PDF, se enviado
            if uploaded_pdf:
                input_text = extract_text_from_pdf(uploaded_pdf)
            elif manual_text:
                input_text = manual_text
            else:
                st.warning("Por favor, envie um PDF ou digite um texto.")
                return
            
            if input_text:
                # Limita o tamanho do texto para evitar problemas com a API
                input_text = input_text[:5000]
                
                # Gera áudio de forma assíncrona
                audio_data = asyncio.run(generate_audio(
                    input_text, 
                    selected_voice, 
                    selected_format
                ))
                
                if audio_data:
                    # Reproduz o áudio
                    st.audio(audio_data, format=f'audio/{selected_format}')
                    
                    # Opção para download
                    st.download_button(
                        label=f"Baixar Áudio (.{selected_format})",
                        data=audio_data,
                        file_name=f"audio_gerado.{selected_format}",
                        mime=f"audio/{selected_format}"
                    )
    else:
        st.info("Por favor, insira sua chave de API da OpenAI para continuar.")

if __name__ == "__main__":
    main()
