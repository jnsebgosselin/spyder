# -*- coding: utf-8 -*-

# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Spyder Language Server Protocol Client document handler routines."""

import os.path as osp

from spyder.py3compat import PY2
from spyder.config.base import debug_print
from spyder.plugins.editor.lsp import (
    LSPRequestTypes, InsertTextFormat, CompletionItemKind,
    ClientConstants)
from spyder.plugins.editor.lsp.decorators import handles, send_request

if PY2:
    import pathlib2 as pathlib
    from urlparse import urlparse
else:
    import pathlib
    from urllib.parse import urlparse


def path_as_uri(path):
    return pathlib.Path(osp.abspath(path)).as_uri()


class DocumentProvider:
    def register_file(self, filename, signal):
        filename = path_as_uri(filename)
        if filename not in self.watched_files:
            self.watched_files[filename] = []
        self.watched_files[filename].append(signal)

    @handles(LSPRequestTypes.DOCUMENT_PUBLISH_DIAGNOSTICS)
    def process_document_diagnostics(self, response, *args):
        uri = response['uri']
        diagnostics = response['diagnostics']
        callbacks = self.watched_files[uri]
        for callback in callbacks:
            callback.emit(
                LSPRequestTypes.DOCUMENT_PUBLISH_DIAGNOSTICS,
                {'params': diagnostics})

    @send_request(
        method=LSPRequestTypes.DOCUMENT_DID_CHANGE, requires_response=False)
    def document_changed(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file']),
                'version': params['version']
            },
            'contentChanges': [{
                'text': params['text']
            }]
        }
        return params

    @send_request(
        method=LSPRequestTypes.DOCUMENT_DID_OPEN, requires_response=False)
    def document_open(self, editor_params):
        uri = path_as_uri(editor_params['file'])
        if uri not in self.watched_files:
            self.register_file(editor_params['file'], editor_params['signal'])
        params = {
            'textDocument': {
                'uri': uri,
                'languageId': editor_params['language'],
                'version': editor_params['version'],
                'text': editor_params['text']
            }
        }

        return params

    @send_request(method=LSPRequestTypes.DOCUMENT_COMPLETION)
    def document_completion_request(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file'])
            },
            'position': {
                'line': params['line'],
                'character': params['column']
            }
        }

        return params

    @handles(LSPRequestTypes.DOCUMENT_COMPLETION)
    def process_document_completion(self, response, req_id):
        if isinstance(response, dict):
            response = response['items']
        for item in response:
            item['kind'] = item.get('kind', CompletionItemKind.TEXT)
            item['detail'] = item.get('detail', '')
            item['documentation'] = item.get('documentation', '')
            item['sortText'] = item.get('sortText', item['label'])
            item['filterText'] = item.get('filterText', item['label'])
            item['insertTextFormat'] = item.get(
                'insertTextFormat', InsertTextFormat.PLAIN_TEXT)
            item['insertText'] = item.get('insertText', item['label'])

        if req_id in self.req_reply:
            self.req_reply[req_id].emit(
                LSPRequestTypes.DOCUMENT_COMPLETION, {'params': response})

    @send_request(method=LSPRequestTypes.DOCUMENT_SIGNATURE)
    def signature_help_request(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file'])
            },
            'position': {
                'line': params['line'],
                'character': params['column']
            }
        }

        return params

    @handles(LSPRequestTypes.DOCUMENT_SIGNATURE)
    def process_signature_completion(self, response, req_id):
        if len(response['signatures']) > 0:
            response['signatures'] = response['signatures'][
                response['activeSignature']]
        else:
            response = None
        if req_id in self.req_reply:
            self.req_reply[req_id].emit(
                LSPRequestTypes.DOCUMENT_SIGNATURE,
                {'params': response})

    @send_request(method=LSPRequestTypes.DOCUMENT_HOVER)
    def hover_request(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file'])
            },
            'position': {
                'line': params['line'],
                'character': params['column']
            }
        }

        return params

    @handles(LSPRequestTypes.DOCUMENT_HOVER)
    def process_hover_result(self, result, req_id):
        contents = result['contents']
        if isinstance(contents, list):
            contents = contents[0]
        if isinstance(contents, dict):
            contents = contents['value']
        if req_id in self.req_reply:
            self.req_reply[req_id].emit(
                LSPRequestTypes.DOCUMENT_HOVER,
                {'params': contents})

    @send_request(method=LSPRequestTypes.DOCUMENT_DEFINITION)
    def go_to_definition_request(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file'])
            },
            'position': {
                'line': params['line'],
                'character': params['column']
            }
        }

        return params

    @handles(LSPRequestTypes.DOCUMENT_DEFINITION)
    def process_go_to_definition(self, result, req_id):
        if isinstance(result, list):
            if len(result) > 0:
                result = result[0]
                uri = urlparse(result['uri'])
                result['file'] = osp.join(uri.netloc, uri.path)
            else:
                result = None
        if req_id in self.req_reply:
            self.req_reply[req_id].emit(
                LSPRequestTypes.DOCUMENT_DEFINITION,
                {'params': result})

    @send_request(method=LSPRequestTypes.DOCUMENT_WILL_SAVE,
                  requires_response=False)
    def document_will_save_notification(self, params):
        params = {
            'textDocument': {
                'uri': path_as_uri(params['file'])
            },
            'reason': params['reason']
        }
        return params

    @send_request(method=LSPRequestTypes.DOCUMENT_DID_CLOSE,
                  requires_response=False)
    def document_did_close(self, params):
        file_signal = params['signal']
        debug_print('[{0}] File: {1}'.format(
            LSPRequestTypes.DOCUMENT_DID_CLOSE, params['file']))
        filename = path_as_uri(params['file'])

        params = {
            'textDocument': {
                'uri': filename
            }
        }
        if filename not in self.watched_files:
            params[ClientConstants.CANCEL] = True
        else:
            signals = self.watched_files[filename]
            idx = -1
            for i, signal in enumerate(signals):
                if id(file_signal) == id(signal):
                    idx = i
                    break
            if idx > 0:
                signals.pop(idx)

            if len(signals) == 0:
                self.watched_files.pop(filename)
        return params
