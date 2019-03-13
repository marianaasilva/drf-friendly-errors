from __future__ import unicode_literals

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as RestValidationError, \
    ErrorDetail
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework_friendly_errors import settings
from rest_framework_friendly_errors.field_map import FieldMap


class ErrorMessagesMixin(FieldMap):
    FIELD_VALIDATION_ERRORS = {}
    NON_FIELD_ERRORS = {}

    def __init__(self, *args, **kwargs):
        self.registered_errors = {}
        super(ErrorMessagesMixin, self).__init__(*args, **kwargs)

    @property
    def errors(self):
        ugly_errors = super(ErrorMessagesMixin, self).errors
        pretty_errors = self.build_pretty_errors(ugly_errors)
        return ReturnDict(pretty_errors, serializer=self)

    def register_error(self, error_message, field_name=None,
                       error_key=None, error_code=None):
        if field_name is None:
            if error_code is None:
                raise ValueError('For non field error you must provide '
                                 'an error code')
            error = {'non_field_errors': [{'code': error_code,
                                          'message': error_message}]}
            key = '%s_%s_%s' % (error_message, error_code, field_name)
        else:
            key = field_name
            field_instance = self.fields.get(field_name)
            if field_instance is None:
                raise ValueError('Incorrect field name')
            field_type = field_instance.__class__.__name__
            if error_key is None and error_code is None:
                raise ValueError('You have to provide either error key'
                                 ' or error code')
            if error_code is not None:
                error_code = error_code
            else:
                try:
                    error_code = settings.FRIENDLY_FIELD_ERRORS[
                        field_type].get(
                        error_key)
                except KeyError:
                    raise ValueError('Unknown field type: "%s"' % field_type)
                if error_code is None:
                    raise ValueError('Unknown error key: "%s" '
                                     'for field type: "%s"' %
                                     (error_key, field_type))
            error = {field_name: [{'code': error_code,
                                  'message': error_message}]}
        if field_name is not None:
            self.registered_errors[field_name] = error
        else:
            self.registered_errors[key] = error
        raise RestValidationError(self.registered_errors)

    def get_field_kwargs(self, field, field_data):
        field_type = field.__class__.__name__
        kwargs = {
            'data_type': type(field_data).__name__,
            'input_type': type(field_data).__name__
        }
        if field_type in self.field_map['boolean']:
            kwargs.update({'input': field_data})
        elif field_type in self.field_map['string']:
            kwargs.update({'max_length': getattr(field, 'max_length', None),
                           'min_length': getattr(field, 'min_length', None),
                           'value': field_data})
        elif field_type in self.field_map['numeric']:

            kwargs.update({'min_value': field.min_value,
                           'max_value': field.max_value,
                           'decimal_places': getattr(field, 'decimal_places',
                                                     None),
                           'max_decimal_places': getattr(field,
                                                         'decimal_places',
                                                         None),
                           'max_digits': getattr(field, 'max_digits', None)})
            max_digits = kwargs['max_digits']
            decimal_places = kwargs['decimal_places']
            if max_digits is not None and decimal_places is not None:
                whole_digits = max_digits - decimal_places
                kwargs.update({'max_whole_digits': whole_digits})
        elif field_type in self.field_map['date'].keys():
            kwargs.update({'format': self.field_map['date'][field_type]})
        elif field_type in self.field_map['choice']:
            kwargs.update({'input': field_data,
                           'input_type': type(field_data).__name__})
        elif field_type in self.field_map['file']:
            kwargs.update({'max_length': field.max_length,
                           'length': len(field.parent.data.get(
                               field.source, ''))})
        elif field_type in self.field_map['composite']:
            kwargs.update({'input_type': type(field_data).__name__,
                           'max_length': getattr(field, 'max_length', None),
                           'min_length': getattr(field, 'min_length', None)})
        elif field_type in self.field_map['relation']:
            kwargs.update({'pk_value': field_data,
                           'data_type': type(field_data).__name__,
                           'input_type': type(field_data).__name__,
                           'slug_name': getattr(field, 'slug_field', None),
                           'value': field_data})
        else:
            kwargs.update({'max_length': getattr(field, 'max_length', None)})
        return kwargs

    def does_not_exist_many_to_many_handler(self, field, message, kwargs):
        unformatted = field.error_messages['does_not_exist']
        new_kwargs = kwargs
        for value in kwargs['value']:
            new_kwargs['value'] = value
            if unformatted.format(**new_kwargs) == message:
                return True
        return False

    def find_key(self, field, message, field_name):
        kwargs = self.get_field_kwargs(
            field, self.initial_data.get(field_name)
        )
        for key in field.error_messages:
            if key == 'does_not_exist' \
                    and isinstance(kwargs.get('value'), list) \
                    and self.does_not_exist_many_to_many_handler(
                    field, message, kwargs):
                return key
            unformatted = field.error_messages[key]
            if unformatted.format(**kwargs) in message:
                return key
        if getattr(field, 'child_relation', None):
            return self.find_key(field=field.child_relation, message=message,
                                 field_name=field_name)
        return None

    def _run_validator(self, validator, field, message):
        try:
            validator(self.initial_data[field.field_name])
        except (DjangoValidationError, RestValidationError) as err:
            err_message = err.detail[0] \
                if hasattr(err, 'detail') else err.message
            return err_message == message

    def find_validator(self, field, message):
        for validator in field.validators:
            if self._run_validator(validator, field, message):
                return validator

    def get_field_error_entry(self, error, field):
        if field.field_name in self.registered_errors:
            return self.registered_errors[field.field_name]

        if isinstance(error, dict):
            errors = {}
            for key, val in error.items():
                msg = self.find_key(field, val[0], field.field_name)
                print(val[0], msg)
                msg = ('list_field_' + msg) if msg is not None else 'list_field_error'
                print(msg)
                code = settings.FRIENDLY_FIELD_ERRORS.get(field.__class__.__name__, {}).get(msg)
                errors.update({key: [{'code': code, 'message': val[0]}]})
            return {field.field_name: [errors]}

        field_type = field.__class__.__name__

        key = self.find_key(field, error, field.field_name)
        if not key:
            # Here we know that error was raised by a custom field validator
            validator = self.find_validator(field, error)
            if validator:
                try:
                    name = validator.__name__
                except AttributeError:
                    name = validator.__class__.__name__
                code = self.FIELD_VALIDATION_ERRORS.get(name) or \
                       settings.FRIENDLY_VALIDATOR_ERRORS.get(name)
                return {field.field_name: [{'code': code, 'message': error}]}
            # Here we know that error was raised by custom validate method
            # in serializer
            validator = getattr(self, "validate_%s" % field.field_name, None)
            if validator is None:
                code = settings.FRIENDLY_FIELD_ERRORS.get(
                    field_type, {}).get(error)
                return {field.field_name: [{'code': code, 'message': error}]}

            if self._run_validator(validator, field, error):
                name = validator.__name__
                code = self.FIELD_VALIDATION_ERRORS.get(name) or \
                       settings.FRIENDLY_VALIDATOR_ERRORS.get(name)
                return {field.field_name: [{'code': code, 'message': error}]}
        return {field.field_name: [{'code': settings.FRIENDLY_FIELD_ERRORS.get(
            field_type, {}).get(key), 'message': error}]}

    def get_field_error_entries(self, errors, field):
        return [self.get_field_error_entry(error, field) for error in errors]

    def get_non_field_error_entry(self, error):
        if isinstance(error, dict):
            error = list(error.keys())[0]
        elif isinstance(error, ErrorDetail):
            error = str(error)

        for registered_error in self.registered_errors:
            if error in registered_error:
                return registered_error[error][0]

        if settings.INVALID_DATA_MESSAGE.format(
                data_type=type(self.initial_data).__name__) == error:
            return {'non_field_errors': [{'code': settings.
                FRIENDLY_NON_FIELD_ERRORS.get('invalid'), 'message': error}]}
        code = self.NON_FIELD_ERRORS.get(error) or \
               settings.FRIENDLY_NON_FIELD_ERRORS.get(error)
        return {'non_field_errors': [{'code': code, 'message': error}]}

    def get_non_field_error_entries(self, errors):
        return [self.get_non_field_error_entry(error) for error in errors]

    def build_pretty_errors(self, errors):
        pretty = []
        for error_type in errors:
            if error_type == 'non_field_errors':
                pretty.extend(self.get_non_field_error_entries(
                    errors[error_type]))
            else:
                field = self.fields[error_type]
                error = errors[error_type]
                if isinstance(error, dict):
                    error = [list(error.values())[0][0]]
                pretty.extend(
                    self.get_field_error_entries(error, field),
                )
        pretty_errors = {}
        for err in pretty:
            pretty_errors.update(err)
        return pretty_errors
