この行は見出しでない先頭行である（中央設定で無効化済みの MD041 を意図する）．

本 fixture は「中央設定が無効化した規則にだけ違反する」ことを確認する（Issue #117）．
reviewdog 経路が cli2 用設定を読めない場合，以下の行へ inline コメントが付く．

<div>インライン HTML を含む行である（無効化済みの MD033 を意図する）．</div>

```text
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

上の 100 桁の行は無効化済みの MD013（line-length）を意図する．
