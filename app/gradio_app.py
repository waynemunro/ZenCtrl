# Recycled from Ominicontrol 

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

import gradio as gr
import torch
from PIL import Image
from diffusers.pipelines import FluxPipeline
from diffusers import FluxTransformer2DModel

from flux.condition import Condition
from flux.generate import generate
from flux.lora_controller import set_lora_scale

pipe = None
use_int8 = False
model_config = { "union_cond_attn": True, "add_cond_attn": False, "latent_lora": False, "independent_condition": False}

def get_gpu_memory():
    return torch.cuda.get_device_properties(0).total_memory / 1024**3


def init_pipeline():
    global pipe
    offload_folder = "offload_weights"  # Folder to store offloaded weights
    os.makedirs(offload_folder, exist_ok=True)  # Ensure the folder exists
    pipe = None # Initialize pipe to None

    try:
        print("Attempting to initialize pipeline on GPU...")
        if use_int8 or get_gpu_memory() < 33:
            print("Using int8 transformer model configuration.")
            transformer_model = FluxTransformer2DModel.from_pretrained(
                "sayakpaul/flux.1-schell-int8wo-improved",
                torch_dtype=torch.int8,       # Model is int8
                use_safetensors=True,         # Use safetensors
                low_cpu_mem_usage=True,
                device_map="auto",            # Automatically map model to available devices
                offload_folder=offload_folder
            )
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                transformer=transformer_model, # Pass the int8 transformer
                torch_dtype=torch.float16,     # Other components in float16
                use_safetensors=True,         # Use safetensors for other components
                low_cpu_mem_usage=True,
                device_map="auto",            # Automatically map model to available devices
                offload_folder=offload_folder
            )
        else:
            print("Using float16 pipeline configuration.")
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.float16,
                use_safetensors=True,         # Use safetensors
                low_cpu_mem_usage=True,
                device_map="auto",            # Automatically map model to available devices
                offload_folder=offload_folder
            )
        print(f"Pipeline initialized. Target device (from first component, e.g., transformer): {pipe.device if pipe else 'N/A'}")

    except (RuntimeError, MemoryError) as e: # Catch both RuntimeError and MemoryError
        print(f"Error during GPU pipeline initialization ({type(e).__name__}: {e}). Falling back to CPU.")
        pipe = None # Ensure pipe is None before attempting CPU fallback
        try:
            print("Attempting to load FLUX.1-schnell on CPU with float32...")
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.float32,    # Use float32 for CPU compatibility
                use_safetensors=True,         # Use safetensors for CPU fallback
                low_cpu_mem_usage=True,       # Still useful for CPU
                device_map="cpu",             # Explicitly map to CPU
                offload_folder=offload_folder # Still useful for managing shards even on CPU
            )
            print(f"Pipeline initialized on CPU. Target device: {pipe.device if pipe else 'N/A'}")
        except Exception as cpu_e:
            print(f"Failed to initialize pipeline on CPU as well ({type(cpu_e).__name__}: {cpu_e}).")
            pipe = None # Ensure pipe is None if CPU fallback also fails
    
    # Optional: Load additional LoRA weights, put the loaded weights here!
    if pipe is not None:
        try:
            print("Loading LoRA weights...")
            pipe.load_lora_weights("weights/zen2con_1440_17000/pytorch_lora_weights.safetensors",
                adapter_name="subject")
            pipe.set_adapters(["subject"])
            print("LoRA weights loaded and adapter set.")
        except Exception as lora_e:
            print(f"Error loading LoRA weights ({type(lora_e).__name__}: {lora_e}). Proceeding without LoRA.")
    else:
        print("Pipeline not initialized. Skipping LoRA weights loading.")

def paste_on_white_background(image: Image.Image) -> Image.Image:
    """
    Pastes a transparent image onto a white background of the same size.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Create white background
    white_bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    white_bg.paste(image, (0, 0), mask=image)
    return white_bg.convert("RGB")  # Convert back to RGB if you don't need alpha


def process_image_and_text(image, text, steps=8, strength_sub=1.0, strength_spat=1.0, size=1024):
    # center crop image
    w, h, min_size = image.size[0], image.size[1], min(image.size)
    image = image.crop(
        (
            (w - min_size) // 2,
            (h - min_size) // 2,
            (w + min_size) // 2,
        )
    )
    image = image.resize((size, size))
    image = paste_on_white_background(image) #Optional, you can remove this line if you want just make sure the size it matched.
    condition0 = Condition("subject", image, position_delta=(0, size // 16))
    condition1 = Condition("subject", image, position_delta=(0, -size // 16))
    
    if pipe is None:
        init_pipeline()
    
    with set_lora_scale(["subject"], scale=3.0):
        result_img = generate(
            pipe,
            prompt=text.strip(),
            conditions=[condition0, condition1],
            num_inference_steps=steps,
            height=1024,
            width=1024,
            condition_scale = [strength_sub,strength_spat],
            model_config=model_config,
            default_lora=True,
        ).images[0]

    return [condition0.condition, condition1.condition, result_img]


def get_samples():
    sample_list = [
        {
            "image": "samples/1.png",   #place your image path here
            "text": "A man sitting in a yellow chair drinking a cup of coffee",
        }
    ]
    return [[Image.open(sample["image"]), sample["text"]] for sample in sample_list]


demo = gr.Interface(
    fn=process_image_and_text,
    inputs=[
        gr.Image(type="pil"),
        gr.Textbox(lines=2),
        gr.Slider(minimum=2, maximum=28, value=2, label="steps"),
        gr.Slider(minimum=0, maximum=2.0, value=1.0, label="strength_sub"),
        gr.Slider(minimum=0, maximum=2.0, value=1.0, label="strength_spat"),
        gr.Slider(minimum=512, maximum=2048, value=1024, label="size"),
    ],
    outputs=gr.Gallery(
                label="Outputs", show_label=False, elem_id="gallery",
                columns=[3], rows=[1], object_fit="contain", height="auto"
            ),
    title="ZenCtrl / Subject driven generation",
    examples=get_samples(),
)

if __name__ == "__main__":
    import debugpy
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy is listening on port 5678. Attach your debugger now.")
    # Uncomment the next line if you want the script to wait until a debugger is attached.
    # debugpy.wait_for_client() 
    # print("Debugger attached.")

    init_pipeline()
    demo.launch(
        debug=True, # This is Gradio's own debug mode, separate from Python debugger
        # share=True
    )
