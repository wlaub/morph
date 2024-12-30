import os
import time
import math
import json

import crossfiledialog as cfd
import platformdirs

class AppConfig:
    def __init__(self, app_name):
        self.app_name = app_name
        self.config_dir = platformdirs.user_data_dir(app_name)
        self.config_file = os.path.join(self.config_dir, 'state.json')

        self.config = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as fp:
                self.config = json.load(fp)

    def save(self):
        os.makedirs(self.config_dir, exist_ok = True)
        with open(self.config_file, 'w') as fp:
            json.dump(self.config, fp)

    def memory_select(self, callback, **kwargs):
        kwargs['start_dir'] = self.config.get('start_dir', os.path.expanduser('~'))
        result = callback(**kwargs)

        if result == '' or result is None:
            return None

        if not isinstance(result, str):
            ref = result[0]
        else:
            ref = result

        self.config['start_dir'] = os.path.dirname(result)
        self.save()

        return result


