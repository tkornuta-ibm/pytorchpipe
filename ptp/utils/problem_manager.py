# -*- coding: utf-8 -*-
#
# Copyright (C) tkornuta, IBM Corporation 2019
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = "Tomasz Kornuta"

import os.path
import logging
import inspect

from torch.utils.data import DataLoader

import ptp

from ptp.utils.configuration_error import ConfigurationError
from ptp.utils.component_factory import ComponentFactory
from ptp.utils.sampler_factory import SamplerFactory


class ProblemManager(object):
    """
    Class that instantiates and manages problem and associated entities (dataloader, sampler etc.).
    """

    def __init__(self, name, params):
        """
        Initializes the manager.

        :param name: Name of the manager (e.g. 'training', 'validation').

        :param params: 'ParamInterface' object, referring to one of main sections (training/validation/testing).
        :type params: ptp.utils.ParamInterface

        """
        self.name = name
        self.params = params

        # Initialize the logger.
        self.logger = logging.getLogger(name)

        # Set a default configuration section for data loader.
        dataloader_config = {
            'problem' : {
                'batch_size': 64, # Default batch size.
            },
            'dataloader': {
                'shuffle': True,  # shuffle set by default.
                'batch_sampler': None,
                'num_workers': 0,  # Do not use multiprocessing by default - for now.
                'pin_memory': False,
                'drop_last': False,
                'timeout': 0
                },
            'sampler': {},  # not using sampler by default
            }

        self.params.add_default_params(dataloader_config)


    def build(self, log=True):
        """
        Method creates a problem on the basis of configuration section.

        :param params: Parameters used to instantiate the problem/sampler/data loader etc.
        :type params: ``utils.param_interface.ParamInterface``

        :param log_errors: Logs the detected errors (DEFAULT: TRUE)

        :return: problem object (or None when faced errors)
        """
        try: 
            # Create component.
            component, class_obj = ComponentFactory.build("problem", self.params["problem"])

            # Check if class is derived (even indirectly) from Problem.
            if not ComponentFactory.check_inheritance(class_obj, ptp.Problem.__name__):
                raise ConfigurationError("Class '{}' is not derived from the Problem class!".format(class_obj.__name__))            

            # Set problem.
            self.problem = component

            # Try to build the sampler.
            self.sampler = SamplerFactory.build(self.problem, self.params['sampler'])

            if self.sampler is not None:
                # Set shuffle to False - REQUIRED as those two are exclusive.
                self.params['dataloader'].add_config_params({'shuffle': False})

            # build the DataLoader on top of the validation problem
            self.loader = DataLoader(dataset=self.problem,
                                batch_size=self.params['problem']['batch_size'],
                                shuffle=self.params['dataloader']['shuffle'],
                                sampler=self.sampler,
                                batch_sampler=self.params['dataloader']['batch_sampler'],
                                num_workers=self.params['dataloader']['num_workers'],
                                collate_fn=self.problem.collate_fn,
                                pin_memory=self.params['dataloader']['pin_memory'],
                                drop_last=self.params['dataloader']['drop_last'],
                                timeout=self.params['dataloader']['timeout'],
                                worker_init_fn=self.worker_init_fn)

            # Display sizes.
            if log:
                self.logger.info("Problem for '{}' loaded (size: {})".format(self.name, len(self.problem)))
                if (self.sampler is not None):
                    self.logger.info("Sampler for '{}' created (size: {})".format(self.name, len(self.sampler)))

            # Ok, success.
            return 0

        except ConfigurationError as e:
            if log:
                self.logger.error(e)
            # Return error.
            return 1


    def worker_init_fn(self, worker_id):
        """
        Function to be called by :py:class:`torch.utils.data.DataLoader` on each worker subprocess, \
        after seeding and before data loading. (default: ``None``).

        .. note::

            Set the ``NumPy`` random seed of the worker equal to the previous NumPy seed + its ``worker_id``\
             to avoid having all workers returning the same random numbers.


        :param worker_id: the worker id (in [0, :py:class:`torch.utils.data.DataLoader`.num_workers - 1])
        :type worker_id: int

        :return: ``None`` by default
        """
        # Set random seed of a worker.
        np.random.seed(seed=np.random.get_state()[1][0] + worker_id)

        # Ignores SIGINT signal - what enables "nice" termination of dataloader worker threads.
        # https://discuss.pytorch.org/t/dataloader-multiple-workers-and-keyboardinterrupt/9740/2
        signal.signal(signal.SIGINT, signal.SIG_IGN)
