---
title: "CodablecashをPodmanで隔離ビルドした話"
date: 2026-07-31T00:00:00+09:00
draft: false
tags: ["Codablecash", "Linux"]
---

{{< tweet-card user="iizuka" name="飯塚友裕" id="2079165354836951156" date="2026-07-20" avatar="/images/tweet-avatars/iizuka.jpg" >}}
[Codablecash進捗]
もう少しで、マルチシャードチェーンを動的に拡張ができます。
ここができれば、かなり、今年の夏リリースが現実的になってきます。
{{< /tweet-card >}}

**Codablecash**のネットワーク公開が近づいてきました。マイニング初心者としてまずやっておきたいのが、「ソースコードから自分でビルドして動かせる」ようになっておくことです。今回はその予行演習として、隔離環境でのビルドから、同梱テストを全部走らせるところまでやってみました。

## Podmanのコンテナ

{{< figure src="/images/podman-logo.png" alt="Podmanのロゴ" caption="画像は[Podman公式リポジトリ](https://github.com/containers/podman)より" class="logo-on-white" width="420" >}}

今回はビルド環境として**Podman**を使います。Dockerと同じコンテナの道具ですが、**root権限の常駐サービスなしで、一般ユーザーのまま動かせる**（ルートレス）のが売りです。

コンテナを使うことで一種の「檻」のようなものをPC内に作ることができ、ビルドのたびに新しい檻が建ち、終わると丸ごと消えます。一方ビルドの成果物が消えずに残るのは、ソースコードのフォルダだけを檻の中に「窓」として見せているから。**檻の中から見えるのはそのフォルダだけ**で、ホームディレクトリなどの外の環境は、檻の中からは見えません。

コンテナは苦手ですが、検証環境を作るには本当に便利です。

そんな檻の仕様はこの5点になります。

| オプション | 意味 |
|---|---|
| `--userns=keep-id` | 檻の中でも非rootの一般ユーザーで動く |
| `--cap-drop=ALL` + `--security-opt=no-new-privileges` | 特権を全部没収、昇格も禁止 |
| `--network=none` | ビルド中は通信を遮断（依存は檻の金型に同梱済み） |
| `--read-only` + `--tmpfs /tmp` | 檻の床は書き込み禁止、メモ机だけ書ける |
| `-v ./codablecash:/work` | ソースのフォルダ**だけ**をマウント |

以降の作業は、専用フォルダを1つ作ってその中で行います（`-v`の相対パスがここを起点になるためです）。

```console
$ mkdir codablecash-lab && cd codablecash-lab
```

檻の金型（イメージ）は、このContainerfileを同フォルダに保存して作ります。ポイントは、ビルドに必要な道具を全部ここで入れてしまい、ビルド時にはネットワークを不要にすることです。ビルド（cmakeやmake）は実は任意のコマンドを実行できる工程なので、通信を遮断しておけば「ビルド中に外から何かを取ってくる・外へ何かを送る」類の挙動を構造的に封じられます。そして遮断したままビルドが通れば、意図しない外部依存がないことの確認にもなります。

```dockerfile
FROM docker.io/library/ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# 必須: cmake / g++ / make / libgmp-dev。あとはテスト・解析用
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates cmake g++ make libgmp-dev \
        lcov cppcheck valgrind git \
    && rm -rf /var/lib/apt/lists/*

# ubuntu:24.04は既定でuid 1000の"ubuntu"ユーザーを持つので、
# ホストの自分(uid 1000)に対応するbuilderユーザーに置き換える
RUN userdel -r ubuntu 2>/dev/null || true; \
    groupadd -g 1000 builder \
    && useradd -m -u 1000 -g 1000 -s /bin/bash builder

USER builder
WORKDIR /work
CMD ["/bin/bash"]
```

そうして、イメージを実際に作るコマンドはこちらです。

```console
$ podman build -t codablecash-build:24.04 -f Containerfile .
```

## 「ビルド」の必要性

私は普段PHPを少し書く程度で、C++のビルドは今回が初体験でした。PHPはソースを置けば基本そのまま動きます。ですが、C++は実行する前に、ソース全体を機械語に翻訳し切って実行ファイルを作っておく方式です。

翻訳は2段階で、ソースファイル1つ1つを部品に翻訳する工程（コンパイル）と、部品を全部つなぎ合わせて実行ファイルに組み立てる工程（リンク）に分かれています。

## 公式手順でビルドしてみる

次は、先ほど作ったイメージから新しい檻を建てます。

まずはソースを取得して、親ディレクトリで檻を建てて中に入ります。

```console
$ git clone https://github.com/alinous-core/codablecash.git
$ podman run --rm -it --userns=keep-id \
    --security-opt=no-new-privileges --cap-drop=ALL \
    --network=none --read-only --tmpfs /tmp -e HOME=/tmp \
    -v ./codablecash:/work -w /work \
    codablecash-build:24.04 bash
```

檻の中に入ると、コマンドで指定したとおり`/work`ディレクトリにいます。`ls`してみるとcodablecashソースのルートにいるのがわかります。

```console
builder@コンテナID:/work$ ls
AlinousStore.cpp   CODE_OF_CONDUCT.md  README.md	 codablecash.kdev4  docs  src		      src_db   src_smartcontract	  src_smartcontract_vm
CMakeLists.txt	   CONTRIBUTING.md     README.txt	 cppcheck	    img   src_blockchain      src_ext  src_smartcontract_db	  src_test
CMakeReport.cmake  LICENSE	       SETUP_ECLIPSE.md  docker		    sh	  src_blockchain_p2p  src_gen  src_smartcontract_modular  tools
```

さて、ビルド手順は、リポジトリの`sh/README.md`に公式の説明があります。

- `cmakeDebug.sh`：段取り用ファイル
- `maketest.sh`：ビルドとテスト一括用ファイル

この2本立てで実行します。

では早速、まずは段取り用のファイルから。

```console
builder$ ./sh/cmakeDebug.sh
```

実行後、ダーッとテキストが出力され、無事に成功したようです。あっという間に完了しました。

```console
・・・・・・・・・・・・
-- Configuring done (0.5s)
-- Generating done (0.4s)
-- Build files have been written to: /work/target
+ popd
/work
```

そして次のコマンドを実行します。

```console
builder$ ./sh/maketest.sh
```

### エラー発生

`maketest.sh`の実行でエラーとなってしまいました。

```console
---- Block Head -----
 959191f8508f761809e1e37b4554077d3311dc4c5097259a946f244ff8afad44 [height: 1 voted: 0 voting: 0 mev: -1]
---------------------- at file: /work/src_blockchain/bc_status_cache/BlockHead.cpp, line : 263
*********************************************** at file: /work/src_blockchain/bc_status_cache/HeadBlockDetector.cpp, line : 287
./sh/maketest.sh: line 10:  9696 Segmentation fault      (core dumped) ./testall -v
```

ビルドは最後まで通っていて、エラーが出たのはその後のテスト（`./testall`）の途中のようです。調べてみると、どうやらこれは、私の環境由来のようです。同梱のテストには**P2P（ノード同士の通信）の試験が含まれる**ので、通信が遮断された檻では通信が失敗して落ちてしまう。これが原因でした。

そのため、テストの時だけ、`--network=none`を1つ外した檻に入り直します（通信といってもコンテナ内のローカルポート同士です）。

ちなみに「通信を遮断したままビルドが最後まで通った」ということは、ビルド中に外から何かを取ってくる隠れた依存がないことを、ここで確認できたことにもなります。

一旦exitして再度入り直します。今後以下のように`--network=none`不使用のコマンドを使います。

```console
builder$ exit
$ podman run --rm -it --userns=keep-id \
        --security-opt=no-new-privileges --cap-drop=ALL \
        --read-only --tmpfs /tmp -e HOME=/tmp \
        -v ./codablecash:/work -w /work \
        codablecash-build:24.04 bash
```

再度実行します。

```console
builder$ ./sh/cmakeDebug.sh
```

こちらはもちろん問題なし。次はビルドとテストです。

```console
builder$ ./sh/maketest.sh
```

### カバレッジエラー

コマンド実行後はテストコードがごにょごにょと動き、無事に完了！・・・かと思いきや、最後の最後になにやらエラーが出ています。

```console
	Perhaps you need to compile with '-fprofile-update=atomic
(use "geninfo --ignore-errors negative ..." to bypass this error)
make[3]: *** [src_blockchain/bc_block_vote/CMakeFiles/report_blockchain_bc_block_vote.dir/build.make:76: report_blockchain_bc_block_vote] Error 1
make[2]: *** [CMakeFiles/Makefile2:7150: src_blockchain/bc_block_vote/CMakeFiles/report_blockchain_bc_block_vote.dir/all] Error 2
make[1]: *** [CMakeFiles/Makefile2:6134: CMakeFiles/report.dir/rule] Error 2
make: *** [Makefile:134: report] Error 2
```

ただ、よく見るとテスト自体は全部走り切っていて、止まったのはその後に自動で走る「カバレッジ集計（lcov）」の工程のようです。

## テスト2070個完走

カバレッジ集計（lcov）は、テストがコードのどの行を通ったかを集計してくれる仕組みです。新しめのバージョン（Ubuntu 24.04では2.x系）だと検査が厳しく、今回のように途中で止まることがあるようです。設定ファイルを先に置いてから、もう一度実行します。

```console
builder$ printf 'ignore_errors = negative,empty,mismatch,inconsistent,corrupt,unused\n' > /tmp/.lcovrc
builder$ ./sh/maketest.sh   # ビルド済み分は素通りし、テスト実行→カバレッジ集計まで一括
```

そして、やり直した結果がこちらです。

```text
Testing Summary
  100.00% success (Total : 2070, Success 2070, Failed 0)
  Checks(success : 10087, failed :0)
```

**テスト2070個、チェック10087回、全部成功**（所要約12分）。さらに集計が終わると、`target/html_report/`にカバレッジレポート（テストがコードのどの行を通ったかの地図）がHTMLで生成されます。檻を出た後、ホスト側からブラウザで開けます。先頭の集計はこうでした。

```text
Lines: 97.1 %  (79858行中 77529行)
```

約8万行のコードの97.1%が、テストで実際に実行されています。個人開発の実験段階のプロジェクトで、この規模のテストが同梱されていて、しかも全部通る。ツイートで開発者さんの発言を見ているだけでしたが、こうやって手元でそのコードが動いたことにちょっと感動しました。

## まとめ

ビルド自体の所要時間は、4コア8スレッドのi3-10105Tで十数分でした。2000個近い部品（`.o`ファイル）が翻訳されていくログを眺めるのは、初めてだとなかなか壮観です。

- ビルドは「部品に翻訳→組み立て」の2段階。公式手順は`sh/README.md`にある
- テストはP2P試験を含むので、実行時だけネットワーク有りの檻で。lcovの設定は先に仕込む
- このマシンは将来ノードを動かす予定なので、[GDS対策](/posts/gds-mitigation/)に続く防御の一枚としても
