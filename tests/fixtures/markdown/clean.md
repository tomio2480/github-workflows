# clean fixture

このファイルは composite action の統合テスト用に用意した clean ケースである．
GitHub と JavaScript の表記を中央 prh 辞書に従った形で書いている．
JSON Lines のような `JS` を部分文字列として含むだけの語は誤検出しない．
ユーザー登録という表現も中央 prh 辞書では誤検出されない正しい表記である．
装置を正面から見た図のような字義どおりの表現は LLM 定型句として誤検出されない．
<a id="idx-skip-patterns-fixture"></a>数式 $E = IR$ を含むこの 1 文は，記法を除いた見かけで 80 字に収まるため，sentence-length の指摘から skipPatterns で外れる．
