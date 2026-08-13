---
title: "中古ミニPCでCodablecashを掘れるのか検証してみた"
date: 2026-08-14T00:00:00+09:00
draft: false
tags: ["Codablecash", "マイニング"]
cover:
  image: "images/minipc-hashrate-cover.png"
  alt: "テスト用ビルドと最適化ビルドのハッシュレート実測を比べた横棒グラフ。最適化ビルドの8個同時で193.3H/s"
---

Codablecashの公開に備え、マイニング初心者として気になるのが「うちのマシンはどれくらい掘れるのか？」という部分です。
ハードウェアに追加投資すべきかの判断材料にもなるので、ローカルで簡易に実測してみました。

## 計測対象のマシン

- 中古ミニPC（OptiPlex 3080 Micro）
- CPU: Core i3-10105T（4コア8スレッド）
- メモリ: 16GB
- GPUなし（増設も不可）

CodablecashのPoW（マイニングの計算）は、AES・Salsa・SHA256・AstroBWTという複数のハッシュ計算を、ノンスに応じたランダムな順番でつなぐ設計のようです。GPUや専用チップ（ASIC）で殴っても効率が上がりにくい、CPU向けの作りとされています。

つまり、うちのノーマルスペックPCでもマイニングに参加できる嬉しい設計ということです。

## その1: メモリがデュアルチャネルか確認する

PoWに含まれる**AstroBWT**は、CPUの計算能力よりも「メモリからどれだけ速くデータを出し入れできるか」が性能を左右しやすいアルゴリズムです。メモリが1枚挿しか、2枚でデュアルチャネル動作かで帯域は大きく変わるので、まず現状を確認します。

```console
$ sudo dmidecode -t memory | grep -E 'Size|Speed|Locator|Type:'
（関係する行のみ抜粋）
    Size: 8 GB
    Locator: DIMM1
    Type: DDR4
    Speed: 3200 MT/s
    Configured Memory Speed: 2666 MT/s
    Size: 8 GB
    Locator: DIMM2
    Type: DDR4
    Speed: 3200 MT/s
    Configured Memory Speed: 2666 MT/s
```

8GBが2枚、両スロットに1枚ずつ。**既にデュアルチャネルでした**。

なお、メモリ自体は3200MT/s対応品なのに2666MT/sで動いていますが、これはCPU側の対応上限が2666MT/sのためで、仕様通りの動作です。

## その2: 本物のマイニングコードでハッシュレートを測る

暗号資産（仮想通貨）をどれだけ掘れるか？つまり「マイニング力」は、「1秒間に何回ハッシュ計算というくじを引けるか」（ハッシュレート、単位H/s）で決まります。せっかくソースコードが公開されているので、**Codablecash本体のマイニング処理そのもの**を回して測ってみます。

ソースから、マイニングのループは以下のようになっています。

1. ランダムなノンスを作る
2. ブロックの情報とノンスから、ハッシュを計算する
3. ハッシュが難易度の条件を満たしていれば当たり。外れなら1に戻る

この１−３の流れは、同梱テストの中にほぼそのままの形でありました。`src_test/blockchain/pow/test_pow_random_hash.cpp`という、ハッシュを1回だけ計算してみるテストです（呼んでいるのは本体のマイニング処理と同じ関数でした）。

こちらをループで回せば、欲しい値が取れるはず。ということで以下のようなものを作成しました。

```cpp
/*
 * bench_pow.cpp — Codablecashハッシュレート計測
 * 同梱テスト(src_test/blockchain/pow/test_pow_random_hash.cpp)を参考に、
 * 本物のマイニング1回分(createRandomNonce → calcResult)をループで回して数えるだけ。
 * 使い方: ./bench_pow [秒数=30]
 */
#include <chrono>
#include <cstdio>
#include <cstdlib>

#include "pow/PoWNonce.h"
#include "pow/PoWNonceResult.h"
#include "bc_block/BlockHeaderId.h"
#include "bc_block/BlockMerkleRoot.h"
#include "base_timestamp/SystemTimestamp.h"
#include "base/StackRelease.h"

using namespace codablecash;

int main(int argc, char** argv) {
	int seconds = argc > 1 ? atoi(argv[1]) : 30;

	char bin[32];
	for (int i = 0; i < 32; ++i) {
		bin[i] = (char)(i * 7 + 3); // ダミーの前ブロック指紋とマークルルート
	}
	BlockHeaderId bid(bin, 32);
	BlockMerkleRoot root(bin, 32);
	SystemTimestamp tm;

	auto start = std::chrono::steady_clock::now();
	long count = 0;
	double secs = 0;
	while (secs < seconds) {
		PoWNonce* n = PoWNonce::createRandomNonce(); __STP(n);
		PoWNonceResult* r = n->calcResult(&bid, &root, &tm); __STP(r);
		++count;
		secs = std::chrono::duration<double>(
				std::chrono::steady_clock::now() - start).count();
	}
	printf("%.1f秒で%ld回 → %.2f H/s\n", secs, count, count / secs);
	return 0;
}
```

こちらを実行するにあたり、必要な条件は３つあります。

- [公式リポジトリ](https://github.com/alinous-core/codablecash)をcloneして、ビルドとテスト（`./sh/maketest.sh`）が済んでいること
- 上の`bench_pow.cpp`をリポジトリ直下に保存してあること
- コマンドはリポジトリ直下で実行すること

なお、作業はすべてコンテナ（Podman）の中で行っています。以下のプロンプト`builder$`がその中です。

```console
builder$ g++ --coverage -o /tmp/bench_pow bench_pow.cpp \
    -Isrc_blockchain -Isrc_db -Isrc -Isrc_ext \
    target/libcodablecashlib.a target/src_ext/libextlib.a -lpthread -lgmp
```

`-I`はヘッダの場所、最後の2つの`.a`が、テストのときにビルドされたCodablecash本体です。`--coverage`は、本来はこの検証に不要なのですがテスト用ビルドの部品を借りる都合で必要なので（エラーとなってしまう）付与してます。

まずは、この計測プログラムを**1個だけ**起動して30秒測ります。プログラム1個はCPUのコアをおおよそ1個ぶん使って、ひたすら計算します。

```console
builder$ /tmp/bench_pow 30
30.0秒で303回 → 10.09 H/s
```

約10H/sでした。うちのCPUは4コア8スレッドなので、次は同じプログラムを**同時に4個、8個**起動して、全員の合計で見てみます。

```console
builder$ for i in 1 2 3 4; do /tmp/bench_pow 30 & done; wait
30.0秒で296回 → 9.86 H/s
30.0秒で291回 → 9.69 H/s
30.1秒で292回 → 9.72 H/s
30.1秒で292回 → 9.71 H/s

builder$ for i in 1 2 3 4 5 6 7 8; do /tmp/bench_pow 30 & done; wait
30.0秒で160回 → 5.33 H/s
30.0秒で161回 → 5.37 H/s
30.0秒で181回 → 6.03 H/s
30.0秒で180回 → 5.99 H/s
30.1秒で185回 → 6.16 H/s
30.1秒で180回 → 5.99 H/s
30.1秒で185回 → 6.15 H/s
30.1秒で187回 → 6.21 H/s
```

## 結果

集計はただ足しただけですが、以下のような感じになります。

| 条件 | 合算ハッシュレート | 1個比 |
|---|---|---|
| 1個 | 10.1H/s | 1.0倍 |
| 4個同時 | 39.0H/s | 3.9倍 |
| 8個同時（フル負荷） | **47.2H/s** | 4.7倍 |

8個同時実行時でいくと、8人の回数の合計160+161+181+180+185+180+185+187=1,419回を30秒で割って、約47.2H/sになります。

## 考察: 4スレッドと8スレッドがそれほど変わらない

4個（物理コアぶん）までは素直に3.9倍だったのですが。8個にしても+21%しか伸びていません。見かけのスレッドは8個あっても、物理的なコアが4なので、計算そのもので手一杯なこの作業ではスレッドを増やしても伸びが悪いようです。

## 最適化はけっこう効く

実は、ここまでの数字にはまだ伸びしろがあります。計測に使ったCodablecash本体は`./sh/maketest.sh`で作った**テスト用ビルド**で、2つのハンデを背負った状態でした。

- ひとつは**カバレッジ計測入り**であること。先ほど`--coverage`の付与が必要、と書いた通り、計測しながらこのカバレッジも同時に働いている状態でした。（カバレッジとは、「テストがソースコードのどの行を通ったか」を記録する仕組みです）
- もうひとつが**コンパイラの最適化なし**であること、です。

ここでいう「最適化」とは、ソースコードを機械語に翻訳（コンパイル）するときの**推敲**のことです。最適化なしだと、翻訳者は書いてある順番どおりに律儀に訳します。最適化ありだと、意味を変えない範囲で「この計算はループの外で1回やれば済む」「この値はメモリに置かず手元で持ち回そう」と段取りを組み替えながら訳すので、同じ計算結果でも実行速度が数倍変わることがあります。

テスト用ビルドの目的は「正しく動くかの確認」であって速さは必須ではありません。ただ、実際に掘るときに使うのは当然、推敲を全開にしたビルドのほう。そちらの実力も知りたい。ということで、CMakeLists.txtのテスト用ビルドのフラグに`-O3`（最適化を最大にする指定）を足して本体を作り直し、同じ計測をやり直してみました。

その結果・・・1個で10.09→51.3H/sと**約5倍**。8個同時なら**193.3H/s**となりました！

この結果からもうひとつ分かることがあります。冒頭で「AstroBWTはメモリの出し入れが性能を左右しやすい」と書きましたが、もし本当にメモリとの往復が上限を決めているなら、CPU側の段取りをいくら推敲しても待ち時間は減らないので、5倍にはならないはずです。推敲だけでここまで速くなったということは、少なくともうちの構成では、上限を決めているのは**CPUの計算そのもの**のようです。

というわけで、このマシンの実力値は最適化ビルドの**約190H/s**とみておきます。

## 電気代の見積もり

マイニングで24時間したらどうなるのかな、ということで電気代も見ておきます。CPUのTDPは35W。フル負荷時のシステム全体では50W前後と推定して、

- 50W×24時間×30日=36kWh/月
- 電気代にして**月1,300円前後**（35円/kWhで計算）

といったところです。このマシンはもともと24時間稼働させているので、厳密な増分はもう少し小さいはずですが、単純計算だとこのくらいになります。

## まとめ

- 手持ちミニPC（i3-10105T）のCodablecashマイニング力は、最適化ビルドのフル負荷で**約190H/s**（テスト用ビルドなら47.2H/s）
- 4コアまでは素直に伸びる
- ハイパースレッディングはほぼ効かない（最適化ビルドで+4%）
- 最適化（推敲）で約5倍。上限を決めていたのはメモリ帯域ではなく、CPUの計算力だった

