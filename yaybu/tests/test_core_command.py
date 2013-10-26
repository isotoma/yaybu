# coding=utf-8
# Copyright 2013 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest
import mock

from yaybu.core import main


class TestCommand(unittest.TestCase):

    def test_do_help(self):
        self.assertRaises(SystemExit, main.main, ["help"])

    def test_do_help_with_arg(self):
        self.assertRaises(SystemExit, main.main, ["help", "vm"])
