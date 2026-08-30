$runnerArgs = @('-NoProfile', '-File', "$PSScriptRoot\Invoke-SignalOpsDemo.ps1", '-Challenge', '04') + $args
& (Get-Process -Id $PID).Path @runnerArgs
exit $LASTEXITCODE