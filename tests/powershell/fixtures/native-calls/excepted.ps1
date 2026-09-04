# bin/check-native-calls.ps1 の fixture．注記により直接呼びを許す形である．

# native-direct: 失敗は直後の祖先検査が非 0 で終えるため表面化する
git fetch --quiet origin 'refs/tags/v2'

git rev-parse --is-shallow-repository # native-direct: 同上
