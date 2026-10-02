import discord
from discord import app_commands
from discord.ext import commands

# 봇 기본 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --- 파티 모집 View (버튼 및 상호작용) ---
class PartyView(discord.ui.View):
    def __init__(self, mode: str, title: str, start_time: str, max_members: int, leader: discord.Member):
        super().__init__(timeout=None)
        self.mode = mode
        self.title = title
        self.start_time = start_time
        self.max_members = max_members
        self.leader = leader
        
        self.members = [leader]  # 정식 참가자
        self.queue = []          # 대기자 (대기열)
        self.is_closed = False   # 강제 마감 여부

    def make_embed(self):
        # 상태 판별
        if self.is_closed:
            status_str = "🛑 파티 마감"
            color = discord.Color.dark_grey()
        elif len(self.members) >= self.max_members:
            status_str = f"🟡 대기열 모집 중 (정원 완료: {len(self.members)}/{self.max_members})"
            color = discord.Color.gold()
        else:
            status_str = f"🟢 모집 중 ({len(self.members)}/{self.max_members})"
            color = discord.Color.green()

        embed = discord.Embed(
            title=f"⚔️ [{self.mode}] {self.title}",
            description=f"**상태:** {status_str}\n**파티장:** {self.leader.mention}\n**시작 시간:** ⏰ `{self.start_time}`",
            color=color
        )
        
        # 정식 파티원 목록
        member_list_str = "\n".join([f"{idx+1}. {m.mention}" for idx, m in enumerate(self.members)])
        embed.add_field(
            name=f"👥 파티원 ({len(self.members)}/{self.max_members})",
            value=member_list_str if member_list_str else "없음",
            inline=False
        )

        # 대기열 목록
        queue_list_str = "\n".join([f"{idx+1}. {m.mention}" for idx, m in enumerate(self.queue)])
        embed.add_field(
            name=f"⏳ 대기열 ({len(self.queue)}명)",
            value=queue_list_str if queue_list_str else "대기자 없음",
            inline=False
        )

        embed.set_footer(text="아래 버튼을 눌러 파티에 참여하거나 취소하세요.")
        return embed

    @discord.ui.button(label="참여하기 / 대기열 등록", style=discord.ButtonStyle.success, custom_id="party_join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("이미 마감된 파티입니다.", ephemeral=True)
            return

        user = interaction.user
        if user in self.members or user in self.queue:
            await interaction.response.send_message("이미 파티 또는 대기열에 참여 중입니다!", ephemeral=True)
            return

        # 인원이 남아있으면 정식 파티원으로, 다 찼으면 대기열로
        if len(self.members) < self.max_members:
            self.members.append(user)
            msg = "파티원으로 등록되었습니다!"
            if len(self.members) == self.max_members:
                await interaction.channel.send(f"🎉 {self.leader.mention}님, **[{self.mode}]** 파티 정원이 모두 채워졌습니다!")
        else:
            self.queue.append(user)
            msg = f"파티 인원이 가득 차 **대기열 {len(self.queue)}번**으로 등록되었습니다."

        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="참여 취소", style=discord.ButtonStyle.danger, custom_id="party_leave_btn")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        
        if user not in self.members and user not in self.queue:
            await interaction.response.send_message("참여 중인 파티가 아닙니다.", ephemeral=True)
            return

        if user == self.leader and len(self.members) > 1:
            await interaction.response.send_message("파티장은 바로 취소할 수 없습니다. 파티 마감 버튼을 이용해 주세요.", ephemeral=True)
            return

        # 정식 멤버에서 빠지는 경우 -> 대기열 1번 자동 승격
        if user in self.members:
            self.members.remove(user)
            promoted_user = None
            if self.queue:
                promoted_user = self.queue.pop(0)
                self.members.append(promoted_user)

            embed = self.make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            
            if promoted_user:
                await interaction.followup.send(f"🔔 {user.display_name}님의 취소로 대기자 {promoted_user.mention}님이 정식 파티원으로 등록되었습니다!")
            else:
                await interaction.followup.send("파티 참여를 취소했습니다.", ephemeral=True)

        # 대기열에서 빠지는 경우
        elif user in self.queue:
            self.queue.remove(user)
            embed = self.make_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send("대기열 등록이 취소되었습니다.", ephemeral=True)

    @discord.ui.button(label="파티 마감 (파티장 전용)", style=discord.ButtonStyle.secondary, custom_id="party_close_btn")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.leader:
            await interaction.response.send_message("파티장만 파티를 마감할 수 있습니다.", ephemeral=True)
            return

        self.is_closed = True
        for child in self.children:
            child.disabled = True

        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("⚔️ 파티 모집이 파티장에 의해 마감되었습니다.")


# --- 상세 세부사항 입력 팝업(Modal) ---
class PartyDetailModal(discord.ui.Modal):
    def __init__(self, mode: str, max_members: int, is_custom_count: bool):
        super().__init__(title=f"⚔️ {mode} 모집 세부 설정")
        self.mode = mode
        self.max_members = max_members
        self.is_custom_count = is_custom_count

        self.party_title = discord.ui.TextInput(
            label="파티 제목 / 설명",
            placeholder="예: [골플] 즐겜하실 분 구합니다!",
            required=True
        )
        self.add_item(self.party_title)

        self.start_time = discord.ui.TextInput(
            label="시작 시간",
            placeholder="예: 바로 시작 / 10분 뒤 / 21시",
            default="바로 시작",
            required=True
        )
        self.add_item(self.start_time)

        # TFT나 내전처럼 인원을 자유 설정해야 하는 경우만 숫자 입력란 추가
        if self.is_custom_count:
            self.custom_count = discord.ui.TextInput(
                label="모집 인원 (숫자만 입력)",
                placeholder=f"설정 가능 범위: {self.max_members}",
                required=True
            )
            self.add_item(self.custom_count)

    async def on_submit(self, interaction: discord.Interaction):
        final_max = self.max_members

        if self.is_custom_count:
            try:
                val = int(self.custom_count.value)
                if self.mode == "롤토체스" and not (2 <= val <= 8):
                    await interaction.response.send_message("롤토체스는 2명~8명 사이로 입력해 주세요.", ephemeral=True)
                    return
                elif self.mode == "내전" and not (10 <= val <= 20):
                    await interaction.response.send_message("내전은 10명~20명 사이로 입력해 주세요.", ephemeral=True)
                    return
                final_max = val
            except ValueError:
                await interaction.response.send_message("인원수는 숫자로만 입력해 주세요.", ephemeral=True)
                return

        view = PartyView(
            mode=self.mode,
            title=self.party_title.value,
            start_time=self.start_time.value,
            max_members=final_max,
            leader=interaction.user
        )
        embed = view.make_embed()
        await interaction.response.send_message(embed=embed, view=view)


# --- 모드 선택 Select Dropdown View ---
class ModeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(
        placeholder="🎮 플레이할 게임 모드를 선택하세요!",
        options=[
            discord.SelectOption(label="솔로랭크", description="파티원 2명 고정 (자신 포함)", emoji="⚔️"),
            discord.SelectOption(label="자유랭크", description="파티원 5명 고정 (자신 포함)", emoji="🛡️"),
            discord.SelectOption(label="칼바람 나락", description="파티원 5명 고정 (자신 포함)", emoji="❄️"),
            discord.SelectOption(label="롤토체스", description="파티원 2명~8명 선택 가능", emoji="🎲"),
            discord.SelectOption(label="내전", description="파티원 10명~20명 선택 가능", emoji="🏆"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_mode = select.values[0]

        if selected_mode == "솔로랭크":
            modal = PartyDetailModal(mode="솔로랭크", max_members=2, is_custom_count=False)
        elif selected_mode in ["자유랭크", "칼바람 나락"]:
            modal = PartyDetailModal(mode=selected_mode, max_members=5, is_custom_count=False)
        elif selected_mode == "롤토체스":
            modal = PartyDetailModal(mode="롤토체스", max_members="2~8명", is_custom_count=True)
        elif selected_mode == "내전":
            modal = PartyDetailModal(mode="내전", max_members="10~20명", is_custom_count=True)

        await interaction.response.send_modal(modal)


# --- 봇 이벤트 및 슬래시 명령어 ---
@bot.event
async def on_ready():
    print(f"뱅가드 파티봇 로그인 완료: {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료!")
    except Exception as e:
        print(f"명령어 동기화 실패: {e}")

@bot.tree.command(name="파티생성", description="뱅가드 파티 모집글을 만들어 시작합니다.")
async def party_create(interaction: discord.Interaction):
    await interaction.response.send_message("아래 메뉴에서 모집할 모드를 선택해 주세요!", view=ModeSelectView(), ephemeral=True)


# 봇 토큰 입력 부분 (개발자 센터에서 복사한 토큰을 여기에 넣으세요)
bot.run("MTU1NTU5NjUwMzg0MDU5MjAwMg.G6gQxW.yFmZfE_3J04sm17xYr-dGzNPoRyrxSx1N06cB4")