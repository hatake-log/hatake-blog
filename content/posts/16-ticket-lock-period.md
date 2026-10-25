---
title: "Codablecashのソースコードで、チケットの「ロック期間」の中身を見てみる"
slug: "ticket-lock-period"
date: 2026-10-03T14:40:00+09:00
draft: false
tags: ["暗号資産", "ステーキング", "Codablecash"]
cover:
  image: "images/ticket-lock-period-top.png"
  alt: "Codablecashのチケットとロック期間"
---


[前回の記事](/posts/staking-in-code/)では、コードベースでステーキングの流れを追いました。今回はその中の「ロック期間」だけに絞って、もう少し細かく見てゆきます。

記事内のコード引用は、Codablecashのソースコード[`967b7eb`](https://github.com/alinous-core/codablecash/tree/967b7eb4fc41c568a2c2b05cc63018b51e0d3fa5)（2026年9月8日）のコミットからお借りしています。


{{< tips >}}
Codablecashは開発中のプロジェクトなので、ここに出てくる数値は今後変わる可能性があります。細かい数字ではなく「何がロック期間を決めているのか」という仕組みの部分を読んでいただければと思います。
{{< /tips >}}

## ロック・ロック期間とは

暗号資産（仮想通貨）のステーキングでいう「ロック」は、手持ちのコインを一定期間動かせない状態にすることです。送金も売却もできなくなる代わりに、ネットワークの維持に参加した見返りとして報酬をもらえる、という仕組みで、その「動かせない期間」がロック期間です。

そして、Codablecashのコードベースで見た時に、「ロック」という言葉による定義は特になく、以下のような**UTXO**の種類の変化が、実際のロック期間とマッチしているようでした。

コインはUTXO（未使用の残高のかたまり）として持たれていて、ふつうに送金できるのは`BalanceUtxo`という種類だけです。チケットを買うと、このコインが別の種類に変わります。

| コインの状態 | UTXOの種類 | 送金できる？ |
|---|---|---|
| ふつうの残高 | `BalanceUtxo` | できる |
| チケットを買った後 | `TicketUtxo` | できない |
| 抽選で選ばれて投票した後 | `TicketVotedUtxo` | できない |
| 元本と報酬が戻った後 | `BalanceUtxo` | できる |

送金トランザクション（`BalanceTransferTransaction`）が入力として受け付けるのは`BalanceUtxo`だけなので、`TicketUtxo`や`TicketVotedUtxo`の形になっているあいだは、そのコインを動かす手段がありません。これが事実上の「ロック」ということですね。

なのでこの記事では、ロック期間を次のように定義して読んでいきます。

{{< tips title="ロックの開始と終了" color="sky" >}}

- **開始**: チケット購入のトランザクション（`RegisterTicketTransaction`）がブロックに載り、`BalanceUtxo`が`TicketUtxo`に変わった時点
- **終了**: `TicketUtxo`（または`TicketVotedUtxo`）が使われて、返却先アドレスに`BalanceUtxo`として戻ってきた時点（投票ノードがミスした場合も、元本は`BalanceUtxo`で戻る）

{{< /tips >}}

## チケットの動き

さて、ロックの開始と終了がはっきりしたところで、その間の主人公である**チケット**がどう動いているのかを順に確認します。

1. **チケットを買う**: `registerTicket()`がチケットの控え`VoteTicket`を作り、預け先の投票ノードの`VoterEntry`が持つ`list`の末尾に追加する。このとき買ったブロック高（`height`）が記録される
2. **成熟を待つ**: 買ってから`ticketMatureIntervalHeight`（256ブロック）たつまでは抽選に参加不可
3. **順番を待つ**: `list`は**買った順**に並んでいて、抽選に出せるのは先頭から`capacity`枚（初期値10）まで。それより後ろは、前のチケットが列から抜けるのを待つ
4. **抽選**: 毎ブロック、`TicketVoteSelector`が全投票ノードから集めた`candidateList`の中から5枚（`votePerBlock`）を選ぶ
5. **投票して、戻ってくる**: 選ばれたチケットは`removeVotedTicket()`で`list`から外れ、次のブロックで投票ノードが`VoteBlockTransaction`を出す。そのブロックで元本と報酬が返却先に戻る
6. **救済措置**: 買ってから`ticketExpireHeight`（43,200ブロック）たっても選ばれていないチケットは`expiredList`に入り、`candidateList`より先に選ばれる


では、1から順にコードを見ていきましょう。

## チケット購入と、その時の「ブロック高」

{{< tips title="コインの状態" color="sky" >}}

`BalanceUtxo` → `TicketUtxo`。前章の定義でいう**ロックの開始**はここです。

ややこしいですが、`VoteTicket`というのはコイン自身ではなく投票ノード側が持つ「控え」のようなものです。
{{< /tips >}}

まずは、チケット購入のトランザクションがブロックに取り込まれる場面です。

ノードは`registerTicket()`という関数で「チケットの控え」（`VoteTicket`）を作り、その投票ノードの`VoterEntry`に控えを追加します。`VoterEntry`は**投票ノード1つぶんの登録情報で、預けられたチケットを並べた`list`を持っています**。

```cpp
// src_blockchain/bc_finalizer/VoteTicket.cpp
VoteTicket* VoteTicket::toVoteTicket(uint64_t height, const TicketUtxo *ticketUtxo, const AddressDescriptor* voterAddressDesc) {
	// ・・・・・
	VoteTicket* ticket = new VoteTicket();
	ticket->setHeight(height);                                // 買ったときのブロック高
	ticket->setUtxoId(ticketUtxo->getId());                   // どのチケットか
	ticket->setNodeIdentifier(ticketUtxo->getNodeIdentifier()); // 投票を任せるノード
	ticket->setAddressDesc(ticketUtxo->getAddress());          // 元本の返却先
	ticket->setTicketPrice(ticketUtxo->getAmount());           // ロックした額
	ticket->setVoterAddressDesc(voterAddressDesc);             // 投票ノードの報酬受取先

	return ticket;
}
```

`toVoteTicket()`の呼び出し側では、第1引数の`height`に「チケット購入のトランザクションが載ったブロックのヘッダ」の高さが渡されていました。

```cpp
// src_blockchain/bc_status_cache_context/StatusCacheContext.cpp
void StatusCacheContext::registerTicket(const BlockHeader *header, const RegisterTicketTransaction *trx) {
	TicketUtxo* ticketUtxo = trx->getTicketUtxo();
	const NodeIdentifier* nodeId = ticketUtxo->getNodeIdentifier();

	const VoterEntry* entry = getVoterEntry(nodeId);   // nodeIdからVoterEntryを探す
	// ・・・・・
	VoteTicket* ticket = VoteTicket::toVoteTicket(header->getHeight(), ticketUtxo, voterAddress); __STP(ticket);

	const_cast<VoterEntry*>(entry)->addTicket(ticket);  // VoterEntryのlistの末尾に追加
	// ・・・・・
}
```

日付や時刻ではなく**ブロック高で記録**しています。ロック期間を測るベースとして使われているようです。


もう一つ地味に大事な点として、`addTicket()`は`list->addElement()`で、`list`の**末尾に追加**しています。つまり`VoterEntry`の`list`の中で、**チケットは買った順に並んでいる**ようです。

なんとなく「抽選＝ランダム」なイメージでしたが、チケットを買ったらひとまずは列に順番に並ぶ必要があるのですね。

## 成熟期間は256ブロック

買ったチケットがすぐ抽選に入らないのは、[前回](/posts/staking-in-code/)も出てきた`ticketMatureIntervalHeight`（初期値256）のためです。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->ticketMatureIntervalHeight = 256;
	this->ticketExpireHeight = 20 * 24 * 30 * 3;
	// ・・・・・
}
```

この値がどこで使われているかというと、抽選のたびに候補を集める`makeList()`で「今のブロック高 − 256」を成熟の境界線にして、各投票ノードの`VoterEntry`からチケットを1枚ずつ出させています。

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
void TicketVoteSelector::makeList() {
	resetPosition();

	uint64_t matureHeight = this->height - this->tiketMatureIntervalHeight;  // 今のブロック高 − 256

	bool added = false;
	do{
		added = false;

		int maxLoop = this->list->size();
		for(int i = 0; i != maxLoop; ++i){
			VoterEntry* entry = this->list->get(i);   // 投票ノードを順に回って

			const VoteTicket* ticket = entry->nextTicket(matureHeight);  // 次の1枚を出してもらう
			if(ticket != nullptr){
				addList(ticket);    // 候補に入れる
				added = true;
			}
		}
	}
	while(added);   // 誰も出せなくなるまで繰り返す
}
```

ノード側で「次の1枚」を出す`nextTicket()`がこちら。

```cpp
// src_blockchain/bc_finalizer/VoterEntry.cpp
const VoteTicket* VoterEntry::nextTicket(uint64_t matureHeight) noexcept {
	int size = this->list->size();
	size = size >= this->capacity ? this->capacity : size;   // 出せるのはcapacity枚まで

	if(this->pos >= size || this->list->get(this->pos)->getHeight() > matureHeight){
		return nullptr;   // 上限に達した、または次のチケットがまだ成熟していない
	}

	return this->list->get(this->pos++);   // 先頭から順に1枚出す
}
```

`this->list->get(this->pos)->getHeight() > matureHeight`が成熟の判定です。チケットに記録された「買った高さ」が境界線より新しければ、まだ出せません。`list`は買った順に並んでいるので、成熟していないチケットに当たった時点で、それより後ろも全部まだ、ということになります。

### 抽選に出るのは、`list`の先頭から`capacity`枚

先ほど書いたように、**チケットは買った順に待ちの列に並んでいます**。

`nextTicket()`を見ると、各投票ノードが抽選に出せるのは`list`の**先頭から`capacity`枚まで**のようです。

`capacity`というのは投票ノードごとに持っている枠で、初期値は10。投票を10回成功させるごとに1枠増え、2回続けてミスすると半分に減る、という増減のある枠です（[前回の記事](/posts/staking-in-code/)の`handleVoted()`・`handleMissed()`）。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->voteDefaultCapacity = 10;
	this->voteExtendCapacityCount = 10;
	// ・・・・・
}
```

つまり、あるプールに1,000枚のチケットが預けられていても、そのブロックの抽選に出るのはそのプールの`list`の先頭10枚（`capacity`が育っていればもう少し）だけです。残りの990枚は、前のチケットが選ばれて`list`から抜けるのを、買った順に待つ仕組みです。

ここまでで、一口に「待ち時間」といってもその中には2段階があるということが判明しました。

1. **`list`で順番を待つ**: 預け先のプール（投票ノード）の`VoterEntry`の`list`で、先頭の`capacity`枚に入るまで待つ（先着順）
2. **抽選に当たるのを待つ**: 先頭の`capacity`枚に入ったら、選ばれるまで毎ブロック抽選に出続けて当たるのを待つ

## 抽選と、当たったあと

ブロックごとの抽選で選ばれる枚数は`votePerBlock`（初期値5）です。抽選そのものは[前回の記事](/posts/staking-in-code/)で触れているので、ここではロック期間に関わる2点だけ。

- 先頭の`capacity`枚に入ったチケットから、ブロックの投票権を得る5枚を選ぶ（抽選）
- 抽選に当たったチケットを`list`から削除

まず、`beginBlock()`という「ブロックの処理を始める」関数の中で毎回抽選が行われます。

そのたびに`votePerBlock`枚、つまり5枚が選ばれるのが、以下の部分です。

```cpp
// src_blockchain/bc_status_cache_context/StatusCacheContext.cpp
void StatusCacheContext::beginBlock(const BlockHeader *header, ILockinManager* lockinManager, bool finalize) {
	// ・・・・・
	uint64_t height = header->getHeight();
	TicketVoteSelector selector(list, height, this->config);
	selector.select();   // このブロックの5枚を選ぶ

	{
		const ArrayList<const VoteTicket>* selectedlist = selector.getSelectedList();
		VotingBlockStatus* status = VotingBlockStatus::toVotingBlockStatus(header, selectedlist); __STP(status);
		this->voterCache->storeVotingBlockStatus(status);   // 「このブロックの当選者」として保存

		if(!status->isEmpty()){
			this->voterCache->removeVotedTicket(status);     // 選ばれたチケットをVoterEntryのlistから抜く
		}
	}
}
```

抽選に当たったチケットは、最後の`removeVotedTicket()`で投票ノードの`VoterEntry`の`list`から取り除かれます。

<!-- 中身は、選ばれたチケットごとに`nodeId`から`VoterEntry`を探して、1枚ずつ`removeTicket()`しているだけでした。 -->

<!-- ```cpp
// src_blockchain/bc_status_cache_context_finalizer/VoterStatusMappedCacheContext.cpp
void VoterStatusMappedCacheContext::removeVotedTicket(const VotingBlockStatus *status) {
	const ArrayList<VoteCandidate>* list = status->getCandidatesList();   // このブロックの当選チケット

	int maxLoop = list->size();
	for(int i = 0; i != maxLoop; ++i){
		VoteCandidate* candidate = list->get(i);

		const NodeIdentifier *nodeId = candidate->getNodeIdentifier();
		const VoterEntry* voteEntry = getVoterEntry(nodeId);  // nodeIdからVoterEntryを探す
		// ・・・・・
		const UtxoId* utxoId = candidate->getUtxoId();
		bool deleted = const_cast<VoterEntry*>(voteEntry)->removeTicket(utxoId);   // listから抜く
		// ・・・・・
	}
}
``` -->

`list`から1枚抜けると、後ろのチケットが1つ前に詰まります。

## 当選から返金までは1ブロック

当選したチケットは、指名していた投票ノードが投票（`VoteBlockTransaction`）し、それがブロックに載ると、元本と報酬が返却先アドレスに戻ります。この「当選から返金まで」を見てみます。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->voteBeforeNBlocks = 1;
	this->voteBlockIncludeAfterNBlocks = 1;
	// ・・・・・
}
```

投票トランザクションの検証コードに、この2つを足し算している箇所がありました。

```cpp
// src_blockchain/bc_finalizer_trx/VoteBlockTransaction.cpp
TrxValidationResult VoteBlockTransaction::__validateFinal(・・・・・) const {
	// ・・・・・
	uint16_t voteBeforeNBlocks = config->getVoteBeforeNBlocks(blockHeight);
	uint16_t voteBlockIncludeAfterNBlocks = config->getVoteBlockIncludeAfterNBlocks(blockHeight);

	uint64_t voteTargetBlockHeight = this->voteBlockHeight + voteBeforeNBlocks;        // 抽選が行われたブロック
	uint64_t includeBlockHeight = voteTargetBlockHeight + voteBlockIncludeAfterNBlocks; // 投票を載せるブロック
	// ・・・・・
	if(isSelected && blockHeight == includeBlockHeight){
		return TrxValidationResult::OK;        // 当選していて、載せるべきブロックならOK
	}
	else if(blockHeight > includeBlockHeight){
		return TrxValidationResult::INVALID;   // それより後になったら無効
	}

	return TrxValidationResult::PENDING;       // まだ早い
}
```

- `voteBlockHeight`: 投票の対象になったブロックの高さ
- `voteTargetBlockHeight`: その1つ後、つまり抽選が行われたブロックの高さ
- `includeBlockHeight`: さらに1つ後。投票トランザクションはこのブロックに載せる決まり

つまり投票は、抽選のあった**次のブロック**に載ります。そのブロックで報酬計算（`calcRewords`）と精算トランザクション（`StakeBaseTransaction`。元本＋報酬の返却）も一緒に処理されていました。

{{< tips title="コインの状態" color="sky" >}}

`TicketUtxo` → `TicketVotedUtxo` → `BalanceUtxo`。前章の定義でいう**ロックの終了**はここです。

状態が2段で変わっています。まず`VoteBlockTransaction`が、入力として`TicketUtxo`を使い、出力として`TicketVotedUtxo`を出します（金額と返却先は同じまま）。次に、同じブロックの`StakeBaseTransaction`がその`TicketVotedUtxo`を使って、元本＋報酬ぶんの`BalanceUtxo`を返却先アドレスに出します。投票ノードの取り分は、別の`BalanceUtxo`として投票ノードのアドレスに出ます。

{{< /tips >}}

ブロックの間隔が3分ということを踏まえると、投票ノードは「抽選の次のブロックまでに投票を出す」という締め切りを持つことになります。もし3分ほどノードが止まるとブロックが過ぎてしまい投票ミスとなってしまうので、やはり投票ノードの常時稼働は大事ですね・・・！

## 長く選ばれないチケットは`expiredList`へ

最後に6番。`ticketExpireHeight`（20×24×30×3＝43,200ブロック）を超えて選ばれていないチケットは、通常の`candidateList`ではなく`expiredList`（ソースのコメントでは high priority）に入ります。

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
void TicketVoteSelector::addList(const VoteTicket *ticket) {
	uint64_t ticketHeight = ticket->getHeight();       // このチケットを買ったブロック高
	uint64_t expire = this->height - ticketHeight;    // 買ってから何ブロックたったか

	if(expire < this->ticketExpireHeight){            // 43,200ブロック未満なら
		this->candidateList->addElement(ticket);      // 通常の候補リストへ
	}
	else{
		this->expiredList->addElement(ticket);        // 超えていたら優先リストへ
	}
}
```

`expiredList`にチケットがあれば、その中から先に5枚まで選ばれるという仕組みです。嬉しいですが、その分長く待っていることに変わりはないのでロック期間は長くなってしまいますね。

ただし、この振り分けをする`addList()`は`nextTicket()`が出したチケットにしか呼ばれません。

つまり`list`の先頭`capacity`枚に入っているチケットだけが判定の対象で、なかなか列が進まないプールの後ろで順番を待っているチケットは、90日たっても`expiredList`には入らず、前が抜けるのを待ち続ける形になります。

一方で、長く待った（90日以上かかった）チケットが先頭グループに入ると、その時点ですでに43,200ブロックを超えているのでさくっと`expiredList`に入り、次のブロックで優先的に選ばれます。順番待ちが長かったチケットほど、先頭に来てからは早く抜ける、ということになります。

うーん、難しい。

## ブロック間隔をもとにざっくり計算

ブロック間隔は以下のパラメータにありました。`powBlockTimeMills`が3分（1000ミリ秒×60×3）です。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->powBlockTimeMills = 1000 * 60 * 3;
	// ・・・・・
}
```

この3分を元にして、ソースの定数を時間に換算してみます。

| 項目 | ソースの値 | 時間換算 |
|---|---|---|
| 成熟までの待ち | 256ブロック | 約13時間 |
| 当選・投票から元本が返ってくるまで | 1ブロック | 3分 |
| 買ってから、救済リスト`expiredList`の対象になるまで(※1) | 43,200ブロック（20×24×30×3） | 90日 |
| 平均の待ち時間の目安(※2) | チケット総数÷5枚（1ブロックの出口） | 理想枚数4万枚なら約17日 |

※1については、単純に90日というわけではないので前項の「長く選ばれないチケットは`expiredList`へ」をご確認ください。

※2、「平均の待ち時間」について、どういう計算かというと

ネットワーク全体で4万枚のチケットがあって、毎ブロック5枚ずつ抜けていくなら、1枚のチケットが`list`の先頭に来て抽選で選ばれるまで、平均で4万÷5＝8,000ブロック待つ計算です。

3分間隔なら約17日。

・・・ですが、これはあくまで全体の平均値です。**実際には投票ノードの`capacity`と、待ちの枚数が大きく影響します**。

待ち枚数が多いのに`capacity`が小さいと、その分抽選で抜けるチケットも少ないので順番待ちが長くなります。一方、同じ`capacity`でも待ち枚数が少ないプールだと、その分早く先頭に行くことができます。

このように、実際の投票までの期間は単純計算ではわかりません。目安になるのは全体の枚数ではなく、自分が預けるプールの「待ち枚数と`capacity`のバランス」のほうのようです。


