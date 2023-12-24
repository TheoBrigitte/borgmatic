import subprocess

import pytest
from flexmock import flexmock

from borgmatic import execute as module


@pytest.mark.parametrize(
    'command,exit_code,borg_local_path,expected_result',
    (
        (['grep'], 2, None, True),
        (['grep'], 2, 'borg', True),
        (['borg'], 2, 'borg', True),
        (['borg1'], 2, 'borg1', True),
        (['grep'], 1, None, True),
        (['grep'], 1, 'borg', True),
        (['borg'], 1, 'borg', False),
        (['borg1'], 1, 'borg1', False),
        (['grep'], 0, None, False),
        (['grep'], 0, 'borg', False),
        (['borg'], 0, 'borg', False),
        (['borg1'], 0, 'borg1', False),
        # -9 exit code occurs when child process get SIGKILLed.
        (['grep'], -9, None, True),
        (['grep'], -9, 'borg', True),
        (['borg'], -9, 'borg', True),
        (['borg1'], -9, 'borg1', True),
        (['borg'], None, None, False),
    ),
)
def test_exit_code_indicates_error_respects_exit_code_and_borg_local_path(
    command, exit_code, borg_local_path, expected_result
):
    assert module.exit_code_indicates_error(command, exit_code, borg_local_path) is expected_result


def test_command_for_process_converts_sequence_command_to_string():
    process = flexmock(args=['foo', 'bar', 'baz'])

    assert module.command_for_process(process) == 'foo bar baz'


def test_command_for_process_passes_through_string_command():
    process = flexmock(args='foo bar baz')

    assert module.command_for_process(process) == 'foo bar baz'


def test_output_buffer_for_process_returns_stderr_when_stdout_excluded():
    stdout = flexmock()
    stderr = flexmock()
    process = flexmock(stdout=stdout, stderr=stderr)

    assert module.output_buffer_for_process(process, exclude_stdouts=[flexmock(), stdout]) == stderr


def test_output_buffer_for_process_returns_stdout_when_not_excluded():
    stdout = flexmock()
    process = flexmock(stdout=stdout)

    assert (
        module.output_buffer_for_process(process, exclude_stdouts=[flexmock(), flexmock()])
        == stdout
    )


def test_append_last_lines_under_max_line_count_appends():
    last_lines = ['last']
    flexmock(module.logger).should_receive('log').once()

    module.append_last_lines(
        last_lines, captured_output=flexmock(), line='line', output_log_level=flexmock()
    )

    assert last_lines == ['last', 'line']


def test_append_last_lines_over_max_line_count_trims_and_appends():
    original_last_lines = [str(number) for number in range(0, module.ERROR_OUTPUT_MAX_LINE_COUNT)]
    last_lines = list(original_last_lines)
    flexmock(module.logger).should_receive('log').once()

    module.append_last_lines(
        last_lines, captured_output=flexmock(), line='line', output_log_level=flexmock()
    )

    assert last_lines == original_last_lines[1:] + ['line']


def test_append_last_lines_with_output_log_level_none_appends_captured_output():
    last_lines = ['last']
    captured_output = ['captured']
    flexmock(module.logger).should_receive('log').never()

    module.append_last_lines(
        last_lines, captured_output=captured_output, line='line', output_log_level=None
    )

    assert captured_output == ['captured', 'line']


@pytest.mark.parametrize(
    'full_command,input_file,output_file,environment,expected_result',
    (
        (('foo', 'bar'), None, None, None, 'foo bar'),
        (('foo', 'bar'), flexmock(name='input'), None, None, 'foo bar < input'),
        (('foo', 'bar'), None, flexmock(name='output'), None, 'foo bar > output'),
        (
            ('foo', 'bar'),
            flexmock(name='input'),
            flexmock(name='output'),
            None,
            'foo bar < input > output',
        ),
        (
            ('foo', 'bar'),
            None,
            None,
            {'DBPASS': 'secret', 'OTHER': 'thing'},
            'DBPASS=*** OTHER=*** foo bar',
        ),
    ),
)
def test_log_command_logs_command_constructed_from_arguments(
    full_command, input_file, output_file, environment, expected_result
):
    flexmock(module.logger).should_receive('debug').with_args(expected_result).once()

    module.log_command(full_command, input_file, output_file, environment)


def test_execute_command_calls_full_command():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command)

    assert output is None


def test_execute_command_calls_full_command_with_output_file():
    full_command = ['foo', 'bar']
    output_file = flexmock(name='test')
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=output_file,
        stderr=module.subprocess.PIPE,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stderr=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, output_file=output_file)

    assert output is None


def test_execute_command_calls_full_command_without_capturing_output():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command, stdin=None, stdout=None, stderr=None, shell=False, env=None, cwd=None
    ).and_return(flexmock(wait=lambda: 0)).once()
    flexmock(module).should_receive('exit_code_indicates_error').and_return(False)
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, output_file=module.DO_NOT_CAPTURE)

    assert output is None


def test_execute_command_calls_full_command_with_input_file():
    full_command = ['foo', 'bar']
    input_file = flexmock(name='test')
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=input_file,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, input_file=input_file)

    assert output is None


def test_execute_command_calls_full_command_with_shell():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        ' '.join(full_command),
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=True,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, shell=True)

    assert output is None


def test_execute_command_calls_full_command_with_extra_environment():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env={'a': 'b', 'c': 'd'},
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, extra_environment={'c': 'd'})

    assert output is None


def test_execute_command_calls_full_command_with_working_directory():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd='/working',
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command(full_command, working_directory='/working')

    assert output is None


def test_execute_command_without_run_to_completion_returns_process():
    full_command = ['foo', 'bar']
    process = flexmock()
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(process).once()
    flexmock(module).should_receive('log_outputs')

    assert module.execute_command(full_command, run_to_completion=False) == process


def test_execute_command_and_capture_output_returns_stdout():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command, stderr=None, shell=False, env=None, cwd=None
    ).and_return(flexmock(decode=lambda: expected_output)).once()

    output = module.execute_command_and_capture_output(full_command)

    assert output == expected_output


def test_execute_command_and_capture_output_with_capture_stderr_returns_stderr():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command, stderr=module.subprocess.STDOUT, shell=False, env=None, cwd=None
    ).and_return(flexmock(decode=lambda: expected_output)).once()

    output = module.execute_command_and_capture_output(full_command, capture_stderr=True)

    assert output == expected_output


def test_execute_command_and_capture_output_returns_output_when_process_error_is_not_considered_an_error():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    err_output = b'[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command, stderr=None, shell=False, env=None, cwd=None
    ).and_raise(subprocess.CalledProcessError(1, full_command, err_output)).once()
    flexmock(module).should_receive('exit_code_indicates_error').and_return(False).once()

    output = module.execute_command_and_capture_output(full_command)

    assert output == expected_output


def test_execute_command_and_capture_output_raises_when_command_errors():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command, stderr=None, shell=False, env=None, cwd=None
    ).and_raise(subprocess.CalledProcessError(2, full_command, expected_output)).once()
    flexmock(module).should_receive('exit_code_indicates_error').and_return(True).once()

    with pytest.raises(subprocess.CalledProcessError):
        module.execute_command_and_capture_output(full_command)


def test_execute_command_and_capture_output_returns_output_with_shell():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        'foo bar', stderr=None, shell=True, env=None, cwd=None
    ).and_return(flexmock(decode=lambda: expected_output)).once()

    output = module.execute_command_and_capture_output(full_command, shell=True)

    assert output == expected_output


def test_execute_command_and_capture_output_returns_output_with_extra_environment():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command,
        stderr=None,
        shell=False,
        env={'a': 'b', 'c': 'd'},
        cwd=None,
    ).and_return(flexmock(decode=lambda: expected_output)).once()

    output = module.execute_command_and_capture_output(
        full_command, shell=False, extra_environment={'c': 'd'}
    )

    assert output == expected_output


def test_execute_command_and_capture_output_returns_output_with_working_directory():
    full_command = ['foo', 'bar']
    expected_output = '[]'
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('check_output').with_args(
        full_command, stderr=None, shell=False, env=None, cwd='/working'
    ).and_return(flexmock(decode=lambda: expected_output)).once()

    output = module.execute_command_and_capture_output(
        full_command, shell=False, working_directory='/working'
    )

    assert output == expected_output


def test_execute_command_with_processes_calls_full_command():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(full_command, processes)

    assert output is None


def test_execute_command_with_processes_returns_output_with_output_log_level_none():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    process = flexmock(stdout=None)
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(process).once()
    flexmock(module).should_receive('log_outputs').and_return({process: 'out'})

    output = module.execute_command_with_processes(full_command, processes, output_log_level=None)

    assert output == 'out'


def test_execute_command_with_processes_calls_full_command_with_output_file():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    output_file = flexmock(name='test')
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=output_file,
        stderr=module.subprocess.PIPE,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stderr=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(full_command, processes, output_file=output_file)

    assert output is None


def test_execute_command_with_processes_calls_full_command_without_capturing_output():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command, stdin=None, stdout=None, stderr=None, shell=False, env=None, cwd=None
    ).and_return(flexmock(wait=lambda: 0)).once()
    flexmock(module).should_receive('exit_code_indicates_error').and_return(False)
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(
        full_command, processes, output_file=module.DO_NOT_CAPTURE
    )

    assert output is None


def test_execute_command_with_processes_calls_full_command_with_input_file():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    input_file = flexmock(name='test')
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=input_file,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(full_command, processes, input_file=input_file)

    assert output is None


def test_execute_command_with_processes_calls_full_command_with_shell():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        ' '.join(full_command),
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=True,
        env=None,
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(full_command, processes, shell=True)

    assert output is None


def test_execute_command_with_processes_calls_full_command_with_extra_environment():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env={'a': 'b', 'c': 'd'},
        cwd=None,
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(
        full_command, processes, extra_environment={'c': 'd'}
    )

    assert output is None


def test_execute_command_with_processes_calls_full_command_with_working_directory():
    full_command = ['foo', 'bar']
    processes = (flexmock(),)
    flexmock(module).should_receive('log_command')
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd='/working',
    ).and_return(flexmock(stdout=None)).once()
    flexmock(module).should_receive('log_outputs')

    output = module.execute_command_with_processes(
        full_command, processes, working_directory='/working'
    )

    assert output is None


def test_execute_command_with_processes_kills_processes_on_error():
    full_command = ['foo', 'bar']
    flexmock(module).should_receive('log_command')
    process = flexmock(stdout=flexmock(read=lambda count: None))
    process.should_receive('poll')
    process.should_receive('kill').once()
    processes = (process,)
    flexmock(module.os, environ={'a': 'b'})
    flexmock(module.subprocess).should_receive('Popen').with_args(
        full_command,
        stdin=None,
        stdout=module.subprocess.PIPE,
        stderr=module.subprocess.STDOUT,
        shell=False,
        env=None,
        cwd=None,
    ).and_raise(subprocess.CalledProcessError(1, full_command, 'error')).once()
    flexmock(module).should_receive('log_outputs').never()

    with pytest.raises(subprocess.CalledProcessError):
        module.execute_command_with_processes(full_command, processes)
