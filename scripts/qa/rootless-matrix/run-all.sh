#!/bin/bash
# run-all.sh -- every rootless check, in order. Exit status 0 only if all pass.
here=$(cd "$(dirname "$0")" && pwd); rc=0
echo "##### kernel arguments on every distribution family (real grub-mkconfig / grubby)"; "$here/run-matrix.sh" || rc=1
echo "##### install -> Game Mode plugin -> CLI as a desktop user"; "$here/run-e2e.sh" || rc=1
echo "##### the four release packages with each package manager"; "$here/run-packages.sh" || rc=1
[ $rc -eq 0 ] && echo "ALL MATRIX CHECKS PASSED" || echo "SOME MATRIX CHECKS FAILED"
exit $rc
