$runnerArgs = @('-NoProfile', '-File', "$PSScriptRoot\Invoke-SignalOpsDemo.ps1", '-Challenge', '05') + $args
& (Get-Process -Id $PID).Path @runnerArgs
exit $LASTEXITCODE