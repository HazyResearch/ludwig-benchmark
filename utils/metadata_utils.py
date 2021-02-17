import os
import platform
import datetime

import GPUtil
import ludwig
import numpy as np
import pandas as pd
import psutil
from ludwig.api import LudwigModel
from ludwig.collect import collect_weights
import tensorflow as tf


def get_ludwig_version(**kwargs):
    return ludwig.__version__

def scale_bytes(bytes: int, suffix: str = 'B') -> str:
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]: 
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_hardware_metadata(**kwargs) -> dict:
    """Returns GPU, CPU and RAM information"""

    machine_info = {} 
    # GPU 
    gpus = GPUtil.getGPUs()
    if len(gpus) != 0:
        machine_info['total_gpus'] = len(gpus)
        gpu_type = {}
        for gpu_id, gpu in enumerate(gpus):
            gpu_type[gpu_id] = gpu.name
        machine_info['gpu_info'] = gpu_type
    else: 
        machine_info['total_gpus'] = 0
    # CPU 
    total_cores = psutil.cpu_count(logical=True)
    machine_info['total_cores'] = total_cores
    # RAM
    svmem = psutil.virtual_memory()
    total_RAM = scale_bytes(svmem.total)
    machine_info['RAM'] = total_RAM
    return machine_info

def get_inference_latency(
	model_path: str, 
	dataset_path: str, 
	num_samples: int = 10,
    **kwargs
) -> str:
    """
    Returns avg. time to perform inference on 1 sample
    
    # Inputs
    :param model_path: (str) filepath to pre-trained model (directory that
        contains the model_hyperparameters.json).
    :param dataset_path: (str) filepath to dataset 
    :param dataset_path: (int) number of dev samples to randomly sample 

    # Return
    :return: (str) avg. time per training step
    """

    # Create smaller datasets w/10 samples from original dev set
    full_dataset = pd.read_csv(dataset_path)
    # Note: split == 1 indicates the dev set
    inference_dataset = full_dataset[full_dataset['split'] == 1].sample(
                                                                n=num_samples)
    ludwig_model = LudwigModel.load(model_path)
    start = datetime.datetime.now()
    _, _ = ludwig_model.predict(
        dataset=inference_dataset,
        batch_size=1,
    )
    total_time = datetime.datetime.now() - start
    avg_time_per_sample = total_time/num_samples
    formatted_time = "{:0>8}".format(str(avg_time_per_sample))
    return formatted_time

def get_train_speed(
    model_path: str, 
    dataset_path: str, 
    train_batch_size: int,
    **kwargs
) -> str:
    """
    Returns avg. time per training step

    # Inputs
    :param model_path: (str) filepath to pre-trained model (directory that
        contains the model_hyperparameters.json).
    :param dataset_path: (str) filepath to dataset 

    # Return
    :return: (str) avg. time per training step
    """
    ludwig_model = LudwigModel.load(model_path)
    start = datetime.datetime.now()
    ludwig_model.train_online(
        dataset=dataset_path,
    )
    total_time = datetime.datetime.now() - start
    avg_time_per_minibatch = total_time/train_batch_size
    formatted_time = "{:0>8}".format(str(avg_time_per_minibatch))
    return formatted_time

def get_model_flops(model_path: str, **kwargs) -> int:
    """
    Computes total model flops

    # Inputs
    :param model_path: (str) filepath to pre-trained model.

    # Return
    :return: (int) total number of flops.
    """
    tf.compat.v1.reset_default_graph()
    session = tf.compat.v1.Session()
    graph = tf.compat.v1.get_default_graph()
    flops = None
    with graph.as_default():
        with session.as_default():
            model = LudwigModel.load(model_path)
            run_meta = tf.compat.v1.RunMetadata()
            opts = tf.compat.v1.profiler.ProfileOptionBuilder.float_operation()
            flops = tf.compat.v1.profiler.profile(graph=graph,
                                                  run_meta=run_meta, 
                                                  cmd='op',
                                                  options=opts)
    tf.compat.v1.reset_default_graph()
    session.close()
    return flops.total_float_ops

def get_model_size(model_path: str, **kwargs):
    """ 
    Computes minimum bytes required to store model to memory

    # Inputs
    :param model_path: (str) filepath to pre-trained model.

    # Return
    :return: (int) total bytes 
    :return: (str) total bytes scaled in string format
    """
    tensor_filepaths = collect_weights(
        model_path=model_path, 
        tensors=None,
        output_directory='.model_tensors'
    )
    total_size = 0
    for fp in tensor_filepaths:
        weight_tensor = np.load(fp)
        total_size += weight_tensor.size
    total_bytes = total_size * 32
    scaled_bytes = scale_bytes(total_bytes)
    model_size = {
            'total_bytes' : total_bytes,
            'scaled_bytes' : scaled_bytes
    }
    return model_size

def append_experiment_metadata(
    document: dict, 
    model_path: str, 
    data_path: str,
    train_batch_size: int=16
):
    print("METADATA tracking")
    for key, metrics_func in metadata_registry.items():
        print("currently processing: {}".format(key))
        output = globals()[metrics_func](
            model_path=model_path,
            dataset_path=data_path,
            train_batch_size=train_batch_size
        )
        document.update({
            key : output
        })

metadata_registry = {
    "inference_latency" : "get_inference_latency",
    "time_per_train_step" : "get_train_speed",
    "model_size" : "get_model_size",
    "model_flops" : "get_model_flops",
    "hardware_metadata" : "get_hardware_metadata",
    "ludwig_version" : "get_ludwig_version"
}