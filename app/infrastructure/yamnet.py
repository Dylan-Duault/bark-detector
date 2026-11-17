"""Lazy hardware/model adapter, imported only by the detector process."""
import csv
import os
from pathlib import Path


class Yamnet:
    def __init__(self, settings):
        for key, value in dict(TF_CPP_MIN_LOG_LEVEL='2', OMP_NUM_THREADS='1',
                               TF_NUM_INTEROP_THREADS='1', TF_NUM_INTRAOP_THREADS='1').items():
            os.environ.setdefault(key, value)
        import tensorflow as tf
        import tensorflow_hub as hub
        self.tf = tf
        self.settings = settings
        print('Loading YAMNet model…', flush=True)
        self.model = hub.load('https://tfhub.dev/google/yamnet/1')
        with (Path(__file__).resolve().parents[1] / 'assets/yamnet_class_map.csv').open(newline='') as stream:
            self.classes = [row['display_name'] for row in csv.DictReader(stream)]

    def classify(self, chunk):
        import numpy as np
        scores, _, _ = self.model(chunk)
        means = self.tf.reduce_mean(scores, axis=0).numpy()
        classes = [self.classes[index] for index in means.argsort()[-self.settings.top_n_classes:]]
        volume = float(np.mean(np.abs(chunk)))
        return self.settings.bark_class_name in classes and volume >= self.settings.min_bark_volume, volume
