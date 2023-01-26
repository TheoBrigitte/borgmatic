import csv
import logging
import os

from borgmatic.execute import (
    execute_command,
    execute_command_and_capture_output,
    execute_command_with_processes,
)
from borgmatic.hooks import dump

logger = logging.getLogger(__name__)


def make_dump_path(location_config):  # pragma: no cover
    '''
    Make the dump path from the given location configuration and the name of this hook.
    '''
    return dump.make_database_dump_path(
        location_config.get('borgmatic_source_directory'), 'postgresql_databases'
    )


def make_extra_environment(database):
    '''
    Make the extra_environment dict from the given database configuration.
    '''
    extra = dict()
    if 'password' in database:
        extra['PGPASSWORD'] = database['password']
    extra['PGSSLMODE'] = database.get('ssl_mode', 'disable')
    if 'ssl_cert' in database:
        extra['PGSSLCERT'] = database['ssl_cert']
    if 'ssl_key' in database:
        extra['PGSSLKEY'] = database['ssl_key']
    if 'ssl_root_cert' in database:
        extra['PGSSLROOTCERT'] = database['ssl_root_cert']
    if 'ssl_crl' in database:
        extra['PGSSLCRL'] = database['ssl_crl']
    return extra


EXCLUDED_DATABASE_NAMES = ('template0', 'template1')


def database_names_to_dump(database, extra_environment, log_prefix, dry_run_label):
    '''
    Given a requested database config, return the corresponding sequence of database names to dump.
    In the case of "all" when a database format is given, query for the names of databases on the
    configured host and return them. For "all" without a database format, just return a sequence
    containing "all".
    '''
    requested_name = database['name']

    if requested_name != 'all':
        return (requested_name,)
    if not database.get('format'):
        return ('all',)

    list_command = (
        ('psql', '--list', '--no-password', '--csv', '--tuples-only')
        + (('--host', database['hostname']) if 'hostname' in database else ())
        + (('--port', str(database['port'])) if 'port' in database else ())
        + (('--username', database['username']) if 'username' in database else ())
        + (tuple(database['list_options'].split(' ')) if 'list_options' in database else ())
    )
    logger.debug(
        '{}: Querying for "all" PostgreSQL databases to dump{}'.format(log_prefix, dry_run_label)
    )
    list_output = execute_command_and_capture_output(
        list_command, extra_environment=extra_environment
    )

    return tuple(
        row[0]
        for row in csv.reader(list_output.splitlines(), delimiter=',', quotechar='"')
        if row[0] not in EXCLUDED_DATABASE_NAMES
    )


def dump_databases(databases, log_prefix, location_config, dry_run):
    '''
    Dump the given PostgreSQL databases to a named pipe. The databases are supplied as a sequence of
    dicts, one dict describing each database as per the configuration schema. Use the given log
    prefix in any log entries. Use the given location configuration dict to construct the
    destination path.

    Return a sequence of subprocess.Popen instances for the dump processes ready to spew to a named
    pipe. But if this is a dry run, then don't actually dump anything and return an empty sequence.

    Raise ValueError if the databases to dump cannot be determined.
    '''
    dry_run_label = ' (dry run; not actually dumping anything)' if dry_run else ''
    processes = []

    logger.info('{}: Dumping PostgreSQL databases{}'.format(log_prefix, dry_run_label))

    for database in databases:
        extra_environment = make_extra_environment(database)
        dump_path = make_dump_path(location_config)
        dump_database_names = database_names_to_dump(
            database, extra_environment, log_prefix, dry_run_label
        )

        if not dump_database_names:
            raise ValueError('Cannot find any PostgreSQL databases to dump.')

        for database_name in dump_database_names:
            dump_format = database.get('format', None if database_name == 'all' else 'custom')
            default_dump_command = 'pg_dumpall' if database_name == 'all' else 'pg_dump'
            dump_command = database.get('pg_dump_command') or default_dump_command
            dump_filename = dump.make_database_dump_filename(
                dump_path, database_name, database.get('hostname')
            )
            if os.path.exists(dump_filename):
                logger.warning(
                    f'{log_prefix}: Skipping duplicate dump of PostgreSQL database "{database_name}" to {dump_filename}'
                )
                continue

            command = (
                (dump_command, '--no-password', '--clean', '--if-exists',)
                + (('--host', database['hostname']) if 'hostname' in database else ())
                + (('--port', str(database['port'])) if 'port' in database else ())
                + (('--username', database['username']) if 'username' in database else ())
                + (('--format', dump_format) if dump_format else ())
                + (('--file', dump_filename) if dump_format == 'directory' else ())
                + (tuple(database['options'].split(' ')) if 'options' in database else ())
                + (() if database_name == 'all' else (database_name,))
                # Use shell redirection rather than the --file flag to sidestep synchronization issues
                # when pg_dump/pg_dumpall tries to write to a named pipe. But for the directory dump
                # format in a particular, a named destination is required, and redirection doesn't work.
                + (('>', dump_filename) if dump_format != 'directory' else ())
            )

            logger.debug(
                f'{log_prefix}: Dumping PostgreSQL database "{database_name}" to {dump_filename}{dry_run_label}'
            )
            if dry_run:
                continue

            if dump_format == 'directory':
                dump.create_parent_directory_for_dump(dump_filename)
            else:
                dump.create_named_pipe_for_dump(dump_filename)

            processes.append(
                execute_command(
                    command,
                    shell=True,
                    extra_environment=extra_environment,
                    run_to_completion=False,
                )
            )

    return processes


def remove_database_dumps(databases, log_prefix, location_config, dry_run):  # pragma: no cover
    '''
    Remove all database dump files for this hook regardless of the given databases. Use the log
    prefix in any log entries. Use the given location configuration dict to construct the
    destination path. If this is a dry run, then don't actually remove anything.
    '''
    dump.remove_database_dumps(make_dump_path(location_config), 'PostgreSQL', log_prefix, dry_run)


def make_database_dump_pattern(
    databases, log_prefix, location_config, name=None
):  # pragma: no cover
    '''
    Given a sequence of configurations dicts, a prefix to log with, a location configuration dict,
    and a database name to match, return the corresponding glob patterns to match the database dump
    in an archive.
    '''
    return dump.make_database_dump_filename(make_dump_path(location_config), name, hostname='*')


def restore_database_dump(database_config, log_prefix, location_config, dry_run, extract_process):
    '''
    Restore the given PostgreSQL database from an extract stream. The database is supplied as a
    one-element sequence containing a dict describing the database, as per the configuration schema.
    Use the given log prefix in any log entries. If this is a dry run, then don't actually restore
    anything. Trigger the given active extract process (an instance of subprocess.Popen) to produce
    output to consume.

    If the extract process is None, then restore the dump from the filesystem rather than from an
    extract stream.
    '''
    dry_run_label = ' (dry run; not actually restoring anything)' if dry_run else ''

    if len(database_config) != 1:
        raise ValueError('The database configuration value is invalid')

    database = database_config[0]
    all_databases = bool(database['name'] == 'all')
    dump_filename = dump.make_database_dump_filename(
        make_dump_path(location_config), database['name'], database.get('hostname')
    )
    psql_command = database.get('psql_command') or 'psql'
    analyze_command = (
        (psql_command, '--no-password', '--quiet')
        + (('--host', database['hostname']) if 'hostname' in database else ())
        + (('--port', str(database['port'])) if 'port' in database else ())
        + (('--username', database['username']) if 'username' in database else ())
        + (('--dbname', database['name']) if not all_databases else ())
        + (tuple(database['analyze_options'].split(' ')) if 'analyze_options' in database else ())
        + ('--command', 'ANALYZE')
    )
    pg_restore_command = database.get('pg_restore_command') or 'pg_restore'
    restore_command = (
        (psql_command if all_databases else pg_restore_command, '--no-password')
        + (
            ('--if-exists', '--exit-on-error', '--clean', '--dbname', database['name'])
            if not all_databases
            else ()
        )
        + (('--host', database['hostname']) if 'hostname' in database else ())
        + (('--port', str(database['port'])) if 'port' in database else ())
        + (('--username', database['username']) if 'username' in database else ())
        + (tuple(database['restore_options'].split(' ')) if 'restore_options' in database else ())
        + (() if extract_process else (dump_filename,))
    )
    extra_environment = make_extra_environment(database)

    logger.debug(
        '{}: Restoring PostgreSQL database {}{}'.format(log_prefix, database['name'], dry_run_label)
    )
    if dry_run:
        return

    # Don't give Borg local path so as to error on warnings, as "borg extract" only gives a warning
    # if the restore paths don't exist in the archive.
    execute_command_with_processes(
        restore_command,
        [extract_process] if extract_process else [],
        output_log_level=logging.DEBUG,
        input_file=extract_process.stdout if extract_process else None,
        extra_environment=extra_environment,
    )
    execute_command(analyze_command, extra_environment=extra_environment)
