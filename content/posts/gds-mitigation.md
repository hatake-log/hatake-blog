---
title: "lscpuに一行だけ「Vulnerable」— ミニPCのGDS（Downfall）対策をした話"
date: 2026-07-20T13:30:00+09:00
draft: false
tags: ["Linux", "セキュリティ"]
---

ノード運用に使う予定のPCを整備していたら、思いがけずCPUの脆弱性対策をすることになりました。

## 発端：スペック確認

きっかけは、CPUの素性（Core i3-10105T、4コア8スレッド）を確認しようと`lscpu`を実行した時でした。出力の下の方、Vulnerabilities（脆弱性）という欄が・・・

```text
Vulnerabilities:
  Gather data sampling:  Vulnerable
  Itlb multihit:         KVM: Mitigation: Split huge pages
  Mds:                   Not affected
  Meltdown:              Not affected
  ...
```

他の項目は「Mitigation（緩和済み）」や「Not affected（影響なし）」と並んでいるのに、**一行だけ「Vulnerable（無防備）」**。この欄は、カーネルが「既知のCPU脆弱性を自分はこう扱っています」と自己申告しているリストで、`ls /sys/devices/system/cpu/vulnerabilities/`配下のファイルでも同じ内容が見られます。スペック確認のついでに眺めるだけでも価値のある欄だと、学びました。

## GDS（Downfall）とは

Gather data sampling、通称Downfall。2023年に公表された、Intel第6〜11世代あたりのCPUが持つ設計上の欠陥です（うちのi3-10105Tは第10世代でドンピシャ）。

メモリに散らばったデータを高速にかき集める「Gather命令」の実装に穴があり、同じCPU上で動く別のプログラムが、処理中のデータ（暗号鍵など）を盗み見できてしまいます。

攻撃には「攻撃者のコードが同じマシン上で動いている」ことが必要なので、普段使いのPCなら実害は薄いとされます。ただこのマシンの今後の使い方を考えると、万一侵入されたときにリスクが大きいので穴は塞いでおきたいところです。

## 最初の見立ては外れた

「マイクロコード（Intelが配るCPUの修正プログラム）が古いか入っていないのだろう」と見立てて、Claude Codeに「intel-microcodeの更新とカーネル更新で対策して」と依頼しました。

ところが調査の結果、**マイクロコードは数ヶ月前から導入済みで、毎回の起動でCPUに読み込まれてもいました**。修正データはとっくに手元にあったのです。それなのにVulnerable。

## 真因：カーネルが「既定ではやらない」設定でビルドされていた

犯人はカーネルのビルド設定でした。使用中のカーネルの設定ファイルを見ると：

```console
$ grep GDS /boot/config-$(uname -r)
# CONFIG_MITIGATION_GDS is not set
```

Ubuntuのこのカーネルは、**GDSの緩和機能を「既定では有効にしない」設定で組まれていた**のです。つまり、明示的に「設置して」と指示するまで、修正は眠ったままでした。

なぜ既定オフなのかの公式な理由文までは確認できていませんが、緩和には性能コストがあること、対象CPUが年々古い機種になっていくこと、攻撃にはローカルでのコード実行が前提なことから、「大多数のユーザーには既定オンのコストが見合わない。必要な人はオプトインで」という損得勘定だろうと理解しています。

## 対処：起動オプションで緩和を強制有効化

カーネルへの「指示」は、起動時にGRUB（ブートローダー）が手渡すオプションで伝えられます。作業は3ステップでした。

まず`/etc/default/grub`の該当行に`gather_data_sampling=force`を追記します：

```text
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash gather_data_sampling=force"
```

次に設定を反映して、再起動：

```console
$ sudo update-grub
$ sudo reboot
```

`update-grub`を忘れると、編集した「原稿」が本番の起動メニューに清書されず反映されません。

`force`は「マイクロコードがあればそれを使って緩和せよ。無ければAVXを無効化してでも塞げ」という強い指示です。AVXが無効化になると計算性能への影響が大きいのですが、今回はマイクロコードが揃っていたので、そちらが使われました。

## 検証

再起動後：

```console
$ cat /sys/devices/system/cpu/vulnerabilities/gather_data_sampling
Mitigation: Microcode

$ cat /proc/cmdline
BOOT_IMAGE=/boot/vmlinuz-... ro quiet splash gather_data_sampling=force ...
```

`lscpu`の表示も「Mitigation; Microcode」に変わりました。`/proc/cmdline`は「カーネルが起動時に受け取った指示メモの控え」で、オプションがちゃんと届いたかはここで確認できます。

## 注意点：この設定は「消すと元に戻る」

カーネル起動オプションは**毎回の起動時にその都度手渡される**もので、カーネル側は覚えていません。`/etc/default/grub`から該当記述を消して`update-grub`すれば、次の起動からVulnerableに戻ります。逆に、書いてある限りはカーネルを更新しても`update-grub`が新カーネル用の設定を作ってくれるので、引き継がれます（実際、このマシンではカーネルが一世代上がった今も効いています）。

## まとめ

- `lscpu`のVulnerabilities欄は、カーネルによるCPU脆弱性の取り扱い自己申告。たまに眺める価値あり
- 「Vulnerable＝修正が無い」とは限らない。**修正は届いているのに、有効化されていないだけ**のパターンがある
- `gather_data_sampling=force`は消すと元に戻る。設定した事実ごと記録に残すのが大事
