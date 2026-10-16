import os
import sys
import csv
import struct
import subprocess
from PIL import Image, ImageDraw, ImageFont

from name_input_config import NAME_INPUT_CHARS

sys.stdout.reconfigure(encoding='utf-8')

# This game only maps A-Z, a-z, 0-9 and spaces in its 64-entry
# single-byte font table.  Render required punctuation as custom double-byte
# glyphs.  U+2026 is included because the original font table has no
# Shift-JIS 0x8163 entry for it.
CUSTOM_ASCII_PUNCTUATION = tuple("!?.,-()<>~…")

# These full-width forms consume separate legacy tiles even though an
# equivalent glyph is already available in the custom/single-byte set.
# Normalize only display-equivalent characters; Japanese quotes, middle dots,
# arrows and UI symbols remain native.
RUNTIME_CHARACTER_NORMALIZATION = str.maketrans(
    {
        "×": "X",
        "−": "-",
        "（": "(",
        "）": ")",
        "＜": "<",
        "＞": ">",
        "《": "<",
        "》": ">",
        "·": "・",
        "ー": "-",
        "”": "\"",
        "“": "\"",
        "＋": "+",
        "／": "/",
        "【": "[",
        "】": "]",
    }
)

# Full-width Latin letters and digits duplicate glyphs already present in the
# game's 62 single-byte 0-9/A-Z/a-z tiles.  Store their ASCII equivalents so
# those legacy double-byte entries can be reclaimed for translated names.
RUNTIME_CHARACTER_NORMALIZATION.update(
    {
        **{ord(chr(0xFF10 + i)): chr(ord("0") + i) for i in range(10)},
        **{ord(chr(0xFF21 + i)): chr(ord("A") + i) for i in range(26)},
        **{ord(chr(0xFF41 + i)): chr(ord("a") + i) for i in range(26)},
        # Reuse the existing single/custom glyphs instead of retaining four
        # visually equivalent Japanese double-byte tiles.  These reclaimed
        # entries are required by the completed fixed-name tables.
        ord("\u3000"): " ",
        ord("\uff1d"): "=",
        ord("\uff20"): "@",
        ord("\uff1f"): "?",
        # Korean translations occasionally retain Japanese corner quotes.
        # Render them with the existing custom parentheses so the two legacy
        # quote tiles can be reassigned to required Hangul glyphs.
        ord("\u300c"): "(",
        ord("\u300d"): ")",
    }
)


def normalize_runtime_text(text):
    return text.translate(RUNTIME_CHARACTER_NORMALIZATION)

# High frequency KS X 1001 Korean characters
def get_ks_x_1001_chars():
    chars = []
    common_hangul = (
        "가각간갇갈갉갊감갑값갓갔강갖갗같갚갛개객갠갤갬갭갯갰갱갸갹걋걍걔객거걱건걷걸걺검겁것겄겅겊게겐겔겜겝겟겠겡겨격견결겸겹겻겼경곁계곈곌곕곗고곡곤곧골곪곬곯곰곱곳공곶과곽관괄괆괌괍괏광괘괜괭괴굅굇굉교굔굘굡굣구국군굳굴굵굶굻굼굽굿궁궂궈궉권궐궜궤귀귁귄귈귐귑귓규균귤그극근글긁금급긋긍기긱긴길김깁깃깅깊"
        "까깍깐깔깖깜깝깟깼깡깥깨깩깬깰깸깹깻깼깽꺄꺠꺼꺽껀껄껌껍껏껐껑께껜껠껨껫껭껭껴껸껼꼈꼍계고곡곤골곪곰곱곳공과곽관괄광괘괜괴굉교구국군굴굼굽굿궁궈권궤귀규균귤그극근글금급긋기긴길김깁깃깅"
        "나낙난날낡낢남납낫났낭낮낯낱낳내낵낸낼냄냅냇냈냉냐냑냔냘냥너넉넌널넒넓넘넙넛넜넝네넥넨넬넴넵넷넸넹녀녁년녈념엽녓녔녕녘녜노녹논놀놂놈놉놋농놓놔놘놜놨뇌뇨뇬뇰뇹뇨누눅눈눌눔눕눗nung눠눴눼뉴늰늉느늑는늘늙늚늠늡늦늪늬늰늴니닉닌닐님닙닛닝잎"
        "다닥단달닭닮닯담답닷닜당닻닿대댁댄댈댐댑댓댔댕댜더덕던덜덞덤덥덧덜덩덕데덱덴델뎀뎁뎃뎄뎅뎌뎐뎠뎡뎨도독돈돌돎돔돕돗동돝돠돤돨돼됐되된될됨됩됫됭두둑둔둘둠둡둣둥둬뒀궤뒤뒨뒬뒵뒷듀듄듈듐듀드득든들듥듬듭듯등디딕딘딜딤딥딧딩딪"
        "라락란랄람랍랏랐랑랒랖랗래랙랜랠램랩랫랬랭랴략랸량러럭런럴럼럽럿렀렁레렉렌렐렘렙렛렝려력련렬렴렵렷렸령례롄롼뢰료룐룔룝룟료루룩룬룰룸룹룻룽뤄뤘뤠류륜률륨륫륭르륵른를름릅릇릉릐리릭린릴림립릿링"
        "마막만많말맑맒맘맙맛망맞맡맣매맥맨맬맴맵맷맸맹먀먁먕머먹먼멀멂멈멉멋멍메멕멘멜멤멥멧멩며멱면멸몃몄명몇몌모목몬몰몲몸몹못몽뫄뫈뫘뫼묑묘묜묠묩묫묘무묵문묻물묽묾뭄뭅뭇뭉뭐붠뭘붰뭬뮤뮨뮬뮴뮹므믁믄믈믐믑믯미믹민밀밈밉밋밍및밑"
        "바박반받발밝밞밠밤밥밧방밭배백밴밸뱀뱁뱃뱄뱅뱌버벅번벌범법벗벙베벡벤벨벰벱벳벵벼벽변별볍볏볐병볘보복본볼봄봅봇봉봐봔봤뵈뵘뵤뵨뵬뵵부북분붇불붉붊붐붑붓붕붜붤붰붸뷰뷴률뷩브븍븐블븜븝븟비빅빈빌빔빕빗빙빚빛"
        "사삭산살삶삼삽삿샀상샒새색샌샐샘샙샛샜생샤샥샨샬샴샵샷샹새서석선설섧섬섭섯섰성세섹센셀셈셉셋솄셍셔셕션셜셤셥셧셨셩셰소속손솔솚솜솝솟송놘쇄쇄쇈쇠쇤쇌쇠쇠쇼숀숄숍숏쇼수숙순숟술숨숩숫숭쉬쉭쉰쉴쉼쉽쉿슝스슥슨슬슭슴습슷승시식신실싫심십싯싱싶"
        "아악안앉않알앍앎암압앗았앙앞애액앤앨앰앱앳앴앵야약얀얄얇얌얍얏양얕얗얘얘어억언얹얻얼얽얾엄업엇었엉엌엎에엑엔엘엠엡엣엥여역연열엷염엽엿였영옆예옌옐옙옛오옥온올옭옮옯옴옵옷옹옻와왁완왈왐왔왕왜왝왠왜외왼욀욈외외요욕욘욜욤욥욧용우욱운울욹움웁웃웅워웍원월웠웨웩웬웰웹위윅윈윌윔윕윗유육윤율윰윱윳융윾윽은을읊음읍읏응읜의이익인일읽잃임입잇잉잊잎"
        "자작잔잖잘잚잠잡잣잤장잦재잭재잴잼잽잿쟁쟈쟉쟌쟝쟤저적전절젊점접젓정젖제젝젠젤젬젭젯젱져젼졀졌졍졔조족존졸졺좀좁조종좋좌좐좔좠죄죈죄죠죤죵주죽준줄줆줌줍줏중줘줬줴쥐쥑쥔쥘쥠쥡쥣쥬준쥴쥼쥬즈즉즌즐즘즙즛증지직진질짊짐집짓징짖짙짚"
        "차착찬찰참찹찻찼창찾채책챈챌챔챕챗챙챠챤챵처척천철첨첩첫청체첵첸첼쳄쳅쳇쳉쳐쳔쳤쳥초촉촌촐촘숍촛총촤쵠최쵤최최쵸추축춘출춤춥춧충춰췄췌취췬취츄츈츌츔츄츠측츤츨츰츱층치칙친칠칡침칩칫칭칲"
        "카칵칸칼캄캅캇캉캐객캔캘캠캡캣캥캬커컥컨컬컴컵컷컹케켄켈켐켑켓켕켜켠켤켰켱코콕콘콜콤콥콧콩콰콱콴괄쾌쾨쿄쿠쿡쿤쿨쿰굽굿궁쿼권퀘귀균귤그극근글금급긋기긴길김깁깃깅"
        "타탁탄탈탉탐탑탓탕태택탠탤탬탭탯탱탸터턱턴털텀텁텃텄텅테텍텐텔템텝텟텡텨텬텼텽토톡톤톨톰톱톳통톺톼퇴툉툐투툭툰툴툼툽퉁퉈퉜퉤튀튁튄튈튐튑튕튜튠튤튬튜트특튼틀틥틈틉틋틍틔티틱틴틸팀팁팃팅"
        "파팍판팔팖팜팝팟팠팡팥패팩팬팰팸팹팻팽퍄퍼퍽펀펄펌펍펏펑페펙펜펠펨펩펫펭펴편펼폄펏폈평폐포폭폰폴폼폽폿퐁퐈푀표푠푤표푸푹푼풀붉품풉풋풍풔퓌퓨퓬률퓽프픈플픔픕픗피픽핀필필핍핏핑"
        "하학한할핥함합핫항해핵핵핸핼햄햅햇했행햐허헉헌헐험헙헛헝헤헥헨헬헴헵헷헹혀혁현혈혐협혓혔형혜호혹혼홀홂홈홉홋홍홑화확환활황횃회획횐횔횡효횬횰효후훅훈훌훔훙훠훤훨훵훼훽휀웰휘휙휜휠휨휩휭휴흇흉흐흑흔흘흙흠흡흣흥희흰흴힘"
    )
    for c in common_hangul:
        if c not in chars:
            chars.append(c)
    return chars

# Generate valid unused 2-byte Shift-JIS character codes starting from 0x8140
def get_sjis_safe_codes(count, reserved_codes=None):
    reserved_codes = set(reserved_codes or ())
    codes = []
    # Shift-JIS valid 1st byte: 0x81-0x9F, 0xE0-0xFC
    first_bytes = list(range(0x81, 0x9F + 1)) + list(range(0xE0, 0xFC + 1))
    # Shift-JIS valid 2nd byte: 0x40-0x7E, 0x80-0xFC
    second_bytes = list(range(0x40, 0x7E + 1)) + list(range(0x80, 0xFC + 1))
    
    for f in first_bytes:
        for s in second_bytes:
            code = bytes([f, s])
            if code in reserved_codes:
                continue
            codes.append(code)
            if len(codes) >= count:
                return codes
    return codes

# Hybrid encoder: converts Korean to safe Shift-JIS bytes, keeps original ASCII/symbols
def sjis_hybrid_encode(text, char_to_sjis):
    text = normalize_runtime_text(text)
    result = bytearray()
    for char in text:
        if char in char_to_sjis:
            result.extend(char_to_sjis[char])
        else:
            try:
                # ASCII characters, brackets, numbers fall back to native Shift-JIS
                result.extend(char.encode("shift_jis", errors="strict"))
            except UnicodeEncodeError as exc:
                raise ValueError(
                    f"character cannot be encoded without replacement: {char!r}"
                ) from exc
    return bytes(result)


def collect_native_sjis_codes(texts):
    """Codes that must remain available for punctuation/Japanese fallback."""
    codes = set()
    for text in texts:
        text = normalize_runtime_text(text)
        for char in text:
            if 0xAC00 <= ord(char) <= 0xD7A3:
                continue
            try:
                encoded = char.encode("shift_jis")
            except Exception:
                continue
            if len(encoded) == 2:
                codes.add(encoded)
    return codes


def parse_index4_gim_pixels(gim_data, label):
    """Return the exact index4 pixel payload range from this game's GIM."""
    if gim_data[:12] != b"MIG.00.1PSP\x00":
        raise ValueError(f"{label}: not a PSP little-endian GIM")

    # This resource contains one picture and one image block.  Read the
    # offsets from its headers instead of relying on the previously guessed
    # 0x110 boundary.
    image_block_offset = 0x30
    block_type, block_size, _, header_relative = struct.unpack_from(
        "<IIII", gim_data, image_block_offset
    )
    if block_type != 4:
        raise ValueError(f"{label}: image block type is {block_type}, expected 4")

    image_header_offset = image_block_offset + header_relative
    image_format, pixel_order, width, height = struct.unpack_from(
        "<HHHH", gim_data, image_header_offset + 4
    )
    if image_format != 4:
        raise ValueError(f"{label}: image format is {image_format}, expected index4")
    if (width, height) != (512, 512):
        raise ValueError(f"{label}: unexpected image size {width}x{height}")

    pixel_relative = struct.unpack_from("<I", gim_data, image_header_offset + 0x1C)[0]
    pixel_offset = image_header_offset + pixel_relative
    pixel_size = (width * height) // 2
    pixel_end = pixel_offset + pixel_size
    block_end = image_block_offset + block_size
    if pixel_end != block_end:
        raise ValueError(
            f"{label}: pixel end {pixel_end:#x} does not match image block end {block_end:#x}"
        )

    return pixel_offset, pixel_end, pixel_order

# Swizzler (4bpp Grayscale)
def swizzle_4bpp(grayscale_data, width, height):
    block_w = 32
    block_h = 8
    
    blocks_x = width // block_w
    blocks_y = height // block_h
    
    swizzled = bytearray((width * height) // 2)
    
    dst_idx = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            for y in range(block_h):
                for x in range(0, block_w, 2):
                    real_x = bx * block_w + x
                    real_y = by * block_h + y
                    
                    # Read grayscale pixels (0-255)
                    p1_val = grayscale_data[real_y * width + real_x]
                    p2_val = grayscale_data[real_y * width + real_x + 1]
                    
                    # Scale down to 4-bit (0-15)
                    p1 = int(round(p1_val / 17.0))
                    p2 = int(round(p2_val / 17.0))
                    
                    # Pack into 1 byte (low nibble = p1, high nibble = p2)
                    b = (p1 & 0x0F) | ((p2 & 0x0F) << 4)
                    swizzled[dst_idx] = b
                    dst_idx += 1
                    
    return swizzled


def render_index4_glyph(atlas, tile_index, char, font, tile_size=16):
    """Render an antialiased glyph into a 16-level indexed GIM tile."""
    mask = Image.new("L", (tile_size, tile_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    bbox = mask_draw.textbbox((0, 0), char, font=font)
    glyph_width = bbox[2] - bbox[0]
    glyph_height = bbox[3] - bbox[1]
    position = (
        (tile_size - glyph_width) // 2 - bbox[0],
        (tile_size - glyph_height) // 2 - bbox[1],
    )
    mask_draw.text(position, char, fill=255, font=font)

    tile_x = (tile_index % 32) * tile_size
    tile_y = (tile_index // 32) * tile_size
    atlas_pixels = atlas.load()
    mask_pixels = mask.load()
    for y in range(tile_size):
        for x in range(tile_size):
            atlas_pixels[tile_x + x, tile_y + y] = min(
                15, (mask_pixels[x, y] + 8) // 17
            )

# Parse RESC archive internal files index map (returns list of {name, offset, size})
def parse_res_header(res_data):
    magic = res_data[0:4]
    if magic != b"RESC":
        return None
        
    num_files = struct.unpack("<I", res_data[4:8])[0]
    records = []
    
    # RESC directory starts directly at offset 8, entry size is 16 bytes
    for idx in range(num_files):
        rec_offset = 8 + idx * 16
        name_bytes = res_data[rec_offset : rec_offset + 8]
        # Name is stored in reverse byte order
        name_reversed = name_bytes[::-1]
        name = name_reversed.strip(b'\x00').decode('ascii', errors='ignore').strip()
        
        size, offset = struct.unpack("<II", res_data[rec_offset + 8 : rec_offset + 16])
        records.append({
            "name": name,
            "offset": offset,
            "size": size
        })
        
    return records

def rebuild_sttv1_in_fixed_record(original_data, strings, char_to_sjis):
    """Reflow every STTV string while preserving the outer record size."""
    if len(original_data) < 16 or original_data[:8] != b"STTV1.00":
        raise ValueError("not a complete STTV1.00 table")

    num_strings, table_offset = struct.unpack_from("<II", original_data, 8)
    if table_offset != 0x10:
        raise ValueError(f"unexpected STTV table offset {table_offset:#x}")
    data_offset = table_offset + num_strings * 8
    if data_offset > len(original_data):
        raise ValueError("STTV index table exceeds record size")

    strings_by_index = {}
    for string in strings:
        idx = string["index"]
        if idx in strings_by_index:
            raise ValueError(f"duplicate STTV string index {idx}")
        strings_by_index[idx] = string
    if set(strings_by_index) != set(range(num_strings)):
        raise ValueError(
            f"STTV CSV index coverage mismatch: "
            f"rows={len(strings_by_index)}, strings={num_strings}"
        )

    original_entries = []
    expected_offset = data_offset
    for idx in range(num_strings):
        entry_offset = table_offset + idx * 8
        text_offset, text_length = struct.unpack_from(
            "<II", original_data, entry_offset
        )
        if text_offset != expected_offset or text_offset % 4:
            raise ValueError(f"STTV string {idx} violates offset/alignment rules")
        terminator_offset = text_offset + text_length
        if terminator_offset >= len(original_data):
            raise ValueError(f"STTV string {idx} exceeds record size")
        if original_data[terminator_offset] != 0:
            raise ValueError(f"STTV string {idx} has no null terminator")
        next_offset = (terminator_offset + 4) & ~3
        if next_offset > len(original_data):
            raise ValueError(f"STTV string {idx} padding exceeds record size")
        if any(original_data[terminator_offset + 1 : next_offset]):
            raise ValueError(f"STTV string {idx} has nonzero padding")
        original_entries.append((entry_offset, text_offset, text_length))
        expected_offset = next_offset
    if expected_offset != len(original_data):
        raise ValueError("original STTV strings do not end at the record boundary")

    rebuilt = bytearray(original_data[:data_offset])
    expanded_slots = 0
    max_slot_overflow = 0
    for idx, (entry_offset, text_offset, original_length) in enumerate(
        original_entries
    ):
        string = strings_by_index[idx]
        original_text = original_data[
            text_offset : text_offset + original_length
        ].decode("shift_jis", errors="strict")
        if original_text != string["original"].replace("\r\n", "\n"):
            raise ValueError(f"STTV source mismatch at index {idx}")

        text = string["translated"] if string["translated"] else string["original"]
        encoded = sjis_hybrid_encode(text.replace("\r\n", "\n"), char_to_sjis)
        overflow = max(0, len(encoded) - original_length)
        if overflow:
            expanded_slots += 1
            max_slot_overflow = max(max_slot_overflow, overflow)

        struct.pack_into("<II", rebuilt, entry_offset, len(rebuilt), len(encoded))
        rebuilt.extend(encoded)
        rebuilt.append(0)
        rebuilt.extend(b"\x00" * (((len(rebuilt) + 3) & ~3) - len(rebuilt)))

    content_size = len(rebuilt)
    if content_size > len(original_data):
        raise ValueError(
            f"rebuilt STTV exceeds its fixed record by "
            f"{content_size - len(original_data)} bytes"
        )
    rebuilt.extend(b"\x00" * (len(original_data) - content_size))
    return bytes(rebuilt), {
        "content_size": content_size,
        "remaining_bytes": len(original_data) - content_size,
        "expanded_slots": expanded_slots,
        "max_slot_overflow": max_slot_overflow,
    }


def patch_sttv1_preserving_slots(original_data, strings, char_to_sjis):
    """Patch an STTV table without moving any original string address.

    A few executable-side UI helpers retain direct pointers into etstrtbl
    instead of resolving the STTV index every time.  Reflowing that table
    therefore makes translated entries valid by index but leaves those UI
    helpers reading unrelated bytes.  This path keeps every text offset and
    allocation boundary intact.
    """
    if len(original_data) < 16 or original_data[:8] != b"STTV1.00":
        raise ValueError("not a complete STTV1.00 table")

    num_strings, table_offset = struct.unpack_from("<II", original_data, 8)
    if table_offset != 0x10:
        raise ValueError(f"unexpected STTV table offset {table_offset:#x}")

    strings_by_index = {string["index"]: string for string in strings}
    if len(strings_by_index) != len(strings) or set(strings_by_index) != set(
        range(num_strings)
    ):
        raise ValueError("STTV CSV index coverage mismatch")

    entries = []
    for idx in range(num_strings):
        entry_offset = table_offset + idx * 8
        text_offset, text_length = struct.unpack_from(
            "<II", original_data, entry_offset
        )
        if idx + 1 < num_strings:
            next_offset = struct.unpack_from(
                "<I", original_data, table_offset + (idx + 1) * 8
            )[0]
        else:
            next_offset = len(original_data)
        if not (text_offset + text_length < next_offset <= len(original_data)):
            raise ValueError(f"STTV string {idx} has an invalid fixed slot")
        if original_data[text_offset + text_length] != 0:
            raise ValueError(f"STTV string {idx} has no null terminator")
        entries.append((entry_offset, text_offset, text_length, next_offset))

    rebuilt = bytearray(original_data)
    remaining_bytes = 0
    for idx, (entry_offset, text_offset, original_length, next_offset) in enumerate(
        entries
    ):
        row = strings_by_index[idx]
        original_text = original_data[
            text_offset : text_offset + original_length
        ].decode("shift_jis", errors="strict")
        if original_text != row["original"].replace("\r\n", "\n"):
            raise ValueError(f"STTV source mismatch at index {idx}")

        text = row["translated"] if row["translated"] else row["original"]
        encoded = sjis_hybrid_encode(text.replace("\r\n", "\n"), char_to_sjis)
        capacity = next_offset - text_offset - 1
        if len(encoded) > capacity:
            raise ValueError(
                f"STTV fixed string {idx} exceeds its slot by "
                f"{len(encoded) - capacity} bytes"
            )
        struct.pack_into("<II", rebuilt, entry_offset, text_offset, len(encoded))
        rebuilt[text_offset:next_offset] = (encoded + b"\0").ljust(
            next_offset - text_offset, b"\0"
        )
        remaining_bytes += capacity - len(encoded)

    return bytes(rebuilt), {
        "content_size": len(rebuilt),
        "remaining_bytes": remaining_bytes,
        "expanded_slots": 0,
        "max_slot_overflow": 0,
    }


def patch_in_place():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    game_root = os.path.dirname(workspace_dir)
    original_resource_root = os.path.join(game_root, "Original", "PSP_GAME", "USRDIR", "Resource")
    output_resource_root = os.path.join(game_root, "PSP_GAME", "USRDIR", "Resource")
    total_csv_path = os.path.join(workspace_dir, "total_translation.csv")
    tsqv_csv_path = os.path.join(workspace_dir, "tsqv_translation.csv")
    font_translation_paths = [total_csv_path, tsqv_csv_path]

    # Fixed-name tables use their own CSVs.  Add them to the font mapping only
    # after every row has a translation; a partially translated table remains
    # on the original Japanese data and must not reserve or remap half a set.
    for fixed_csv_name in (
        "wpdttbl_translation.csv",
        "mnstbl_translation.csv",
        "pmprmtbl_translation.csv",
        "mgdttbl_translation.csv",
        "uidttbl_translation.csv",
        "uitmtbl_translation.csv",
        "sidttbl_translation.csv",
        "amdttbl_translation.csv",
        "magictbl_translation.csv",
        "mmgtbl_translation.csv",
        "sitmtbl_translation.csv",
        "magictbl_description_translation.csv",
        "sitmtbl_description_translation.csv",
        "uitmtbl_description_translation.csv",
        "evscript_text/evscript_translation.csv",
    ):
        fixed_csv_path = os.path.join(workspace_dir, fixed_csv_name)
        if not os.path.exists(fixed_csv_path):
            continue
        with open(fixed_csv_path, "r", encoding="utf-8-sig", newline="") as csv_f:
            fixed_rows = list(csv.DictReader(csv_f))
        translated_count = sum(bool(row.get("Translated", "").strip()) for row in fixed_rows)
        if fixed_rows and translated_count == len(fixed_rows):
            font_translation_paths.append(fixed_csv_path)
            print(f"Enabled completed fixed-name CSV for font mapping: {fixed_csv_name}")
        else:
            print(
                f"Skipping incomplete fixed-name CSV: {fixed_csv_name} "
                f"({translated_count}/{len(fixed_rows)})"
            )
    
    print("\n--- ⚡ IN-PLACE BINARY PATCHER STARTED ⚡ ---")
    
    # 1. Scrape unique Korean characters
    unique_korean = []
    missing_translation_paths = [
        path for path in font_translation_paths if not os.path.exists(path)
    ]
    if missing_translation_paths:
        print(f"Error: unified CSV not found: {missing_translation_paths[0]}")
        sys.exit(1)

    print("Scraping unique Korean characters from table and TSQV translations...")
    for translation_path in font_translation_paths:
        with open(translation_path, "r", encoding="utf-8-sig") as csv_f:
            reader = csv.DictReader(csv_f)
            for row in reader:
                translated_text = row.get("Translated", "").replace('\r\n', '\n')
                for char in translated_text:
                    if 0xAC00 <= ord(char) <= 0xD7A3 and char not in unique_korean:
                        unique_korean.append(char)
    for char in NAME_INPUT_CHARS:
        if char not in unique_korean:
            unique_korean.append(char)
    print(
        f"Found {len(unique_korean)} unique Korean characters used across "
        f"{len(font_translation_paths)} unified CSV files."
    )
        
    # Tiles 0..61 contain the full-width alphanumeric glyphs used by the
    # preserved English name page.  Tiles 62..79 were the remaining hiragana
    # glyphs and can be safely reclaimed with the two Japanese name pages now
    # redirected to Korean codes.
    font_chars = list(unique_korean) + list(CUSTOM_ASCII_PUNCTUATION)
    font_tile_start = 62
    font_tile_capacity = (32 * 32) - font_tile_start
    if len(font_chars) > font_tile_capacity:
        print(
            f"Error: {len(font_chars)} custom glyphs exceed the "
            f"{font_tile_capacity}-glyph texture capacity."
        )
        sys.exit(1)
        
    # 2. Open clean original global.res
    orig_global_path = os.path.join(original_resource_root, "global", "global.res")
    if not os.path.exists(orig_global_path):
        print(f"Error: Original global.res not found at {orig_global_path}")
        sys.exit(1)
        
    with open(orig_global_path, "rb") as f:
        global_bytes = bytearray(f.read())
        
    global_records = parse_res_header(global_bytes)
    
    # Debug: Print all available records in global.res
    print("Available files inside global.res:")
    for r in global_records:
        print(f"  - '{r['name']}' (Hex name: {r['name'].encode('ascii', errors='ignore').hex()})")
    
    # Locate "font" GIM inside global.res
    font_record = None
    for r in global_records:
        if r["name"].lower() == "font":
            font_record = r
            break
            
    if not font_record:
        print("Error: Could not locate 'font' file record in global.res header.")
        sys.exit(1)
        
    print(f"Found 'font' GIM in global.res: Offset={hex(font_record['offset'])}, Size={font_record['size']} bytes")

    # Load the original font mapping before assigning Korean byte codes.
    # Codes still used by native punctuation/Japanese text, and every code in
    # the original double-byte map, are excluded to avoid duplicate lookups.
    orig_tbl_path = os.path.join(original_resource_root, "tbldata", "tbldata.res")
    if not os.path.exists(orig_tbl_path):
        print(f"Error: Original tbldata.res not found at {orig_tbl_path}")
        sys.exit(1)
    with open(orig_tbl_path, "rb") as f:
        original_tbldata_bytes = bytearray(f.read())
    original_tbldata_records = parse_res_header(original_tbldata_bytes)
    original_fonttbl = next(
        (r for r in original_tbldata_records if r["name"].lower() == "fonttbl"),
        None,
    )
    if not original_fonttbl:
        print("Error: Could not locate fonttbl in original tbldata.res")
        sys.exit(1)

    fonttbl_start = original_fonttbl["offset"]
    fonttbl_data = original_tbldata_bytes[
        fonttbl_start : fonttbl_start + original_fonttbl["size"]
    ]
    if fonttbl_data[:8] != b"FTTV1.00":
        print("Error: Unexpected fonttbl signature")
        sys.exit(1)
    single_count, double_count, single_offset, double_offset = struct.unpack_from(
        "<HHHH", fonttbl_data, 8
    )
    if double_offset != 0x50:
        print(f"Error: Unexpected fonttbl double-byte offset {double_offset:#x}")
        sys.exit(1)

    original_double_codes = {
        bytes(fonttbl_data[double_offset + i * 2 : double_offset + i * 2 + 2])
        for i in range(double_count)
    }
    all_selected_texts = []
    for translation_path in font_translation_paths:
        with open(translation_path, "r", encoding="utf-8-sig") as csv_f:
            for row in csv.DictReader(csv_f):
                all_selected_texts.append(
                    normalize_runtime_text(
                        row.get("Translated", "") or row.get("Original", "")
                    )
                )
    native_sjis_codes = collect_native_sjis_codes(all_selected_texts)
    reserved_codes = original_double_codes | native_sjis_codes
    sjis_codes = get_sjis_safe_codes(len(font_chars), reserved_codes)
    if len(sjis_codes) != len(font_chars):
        print("Error: Could not allocate enough collision-free Shift-JIS codes")
        sys.exit(1)
    char_to_sjis = {char: sjis_codes[i] for i, char in enumerate(font_chars)}

    # FTTV lookup results are direct GIM tile indices.  Therefore a code
    # stored in double-byte entry N must be rendered into tile N.  Keep the
    # first 62 legacy alphanumeric tiles and every native two-byte character still used by
    # the selected text, then allocate Korean and custom punctuation glyphs
    # from the remaining entry/tile pairs.
    max_mapped_tile = min(double_count, 32 * 32)
    available_tile_indices = []
    for tile_index in range(font_tile_start, max_mapped_tile):
        original_code = bytes(
            fonttbl_data[
                double_offset + tile_index * 2 : double_offset + tile_index * 2 + 2
            ]
        )
        if original_code in native_sjis_codes:
            continue
        available_tile_indices.append(tile_index)

    if len(font_chars) > len(available_tile_indices):
        print(
            f"Error: {len(font_chars)} custom glyphs exceed the "
            f"{len(available_tile_indices)} safe fonttbl/tile pairs."
        )
        sys.exit(1)
    char_to_tile = {
        char: available_tile_indices[i] for i, char in enumerate(font_chars)
    }
    print(
        f"Allocated {len(char_to_sjis)} collision-free custom codes "
        f"({len(unique_korean)} Hangul + {len(CUSTOM_ASCII_PUNCTUATION)} "
        f"custom punctuation); "
        f"mapped them to matching GIM tiles while preserving "
        f"{len(native_sjis_codes)} native two-byte codes."
    )
    
    # 3. Build the Korean font GIM binary
    print("\nRendering Korean font texture sheet (512x512, L-mode)...")
    custom_font_path = os.path.join(os.path.dirname(workspace_dir), "font.ttf")
    font_paths = [
        custom_font_path,
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\gulim.ttc"
    ]
    selected_font = None
    for p in font_paths:
        if os.path.exists(p):
            selected_font = p
            break
            
    if not selected_font:
        print("Error: No system TrueType fonts found.")
        sys.exit(1)
        
    font_size = 14 if os.path.normcase(selected_font) == os.path.normcase(custom_font_path) else 11
    pil_font = ImageFont.truetype(selected_font, font_size)
    print(
        f"Using font: {selected_font} ({pil_font.getname()[0]}, size {font_size})"
    )
    
    # 3. Open original font_real.png to copy its ASCII/numbers (first 80 tiles)
    orig_png_path = os.path.join(workspace_dir, "font_real.png")
    if not os.path.exists(orig_png_path):
        print(f"Error: Original font_real.png not found at {orig_png_path}")
        print("Please ensure font_real.png exists in translation_workspace.")
        sys.exit(1)
        
    img = Image.open(orig_png_path)
    if img.mode != "P":
        print(f"Error: Expected indexed PNG, got mode {img.mode}")
        sys.exit(1)
    
    tile_size = 16
    # Single-byte ASCII uses the same tiles as the full-width forms at the
    # beginning of the double-byte atlas: 0-9, A-Z, a-z (tiles 0-61).
    ascii_tile_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    for tile_index, char in enumerate(ascii_tile_chars):
        render_index4_glyph(img, tile_index, char, pil_font, tile_size)

    for idx, char in enumerate(font_chars):
        # The FTTV entry index and GIM tile index must be exactly identical.
        global_tile_idx = char_to_tile[char]
        render_index4_glyph(img, global_tile_idx, char, pil_font, tile_size)
            
    # Save the updated PNG preview preserving the original palette transparency metadata (tRNS chunk)
    output_png_path = os.path.join(workspace_dir, "font_korean_preview.png")
    orig_transparency = Image.open(orig_png_path).info.get("transparency")
    img.save(output_png_path, transparency=orig_transparency)
    print(f"🎉 Updated font PNG written to: {output_png_path}")
    
    # Compile a PSP little-endian, swizzled index4 GIM.  The generated file is
    # used only as a source of pixels; the original GIM container and palette
    # remain untouched.
    output_gim_path = os.path.join(workspace_dir, "font.gim")
    project_root = os.path.dirname(workspace_dir)
    gimconv_path = os.path.join(project_root, "tool", "GimConv", "GimConv.exe")
    if not os.path.exists(gimconv_path):
        print(f"Error: GimConv.exe not found at {gimconv_path}")
        sys.exit(1)
    if os.path.exists(output_gim_path):
        os.remove(output_gim_path)

    gimconv_command = [
        gimconv_path,
        output_png_path,
        "--format_style", "psp",
        "--format_endian", "little",
        "--image_format", "index4",
        "--palette_format", "rgba8888",
        "--pixel_order", "faster",
        "--output_palette", "off",
        "-s", "512,512",
        "-o", output_gim_path,
    ]
    print("\nCompiling PSP little-endian index4 font GIM...")
    try:
        subprocess.run(gimconv_command, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Error: GimConv failed with exit code {exc.returncode}")
        sys.exit(exc.returncode)

    print(f"Compiled font GIM written to: {output_gim_path}")
    with open(output_gim_path, "rb") as f_gim:
        compiled_gim_bytes = f_gim.read()
        
    # Read original GIM bytes from original global.res
    orig_gim_data = bytearray(global_bytes[font_record["offset"] : font_record["offset"] + font_record["size"]])
    
    original_pixel_start, original_pixel_end, original_pixel_order = parse_index4_gim_pixels(
        orig_gim_data, "original GIM"
    )
    compiled_pixel_start, compiled_pixel_end, compiled_pixel_order = parse_index4_gim_pixels(
        compiled_gim_bytes, "compiled GIM"
    )
    if compiled_pixel_order != original_pixel_order:
        print(
            f"Error: pixel order mismatch (original={original_pixel_order}, "
            f"compiled={compiled_pixel_order})"
        )
        sys.exit(1)

    compiled_pixels = compiled_gim_bytes[compiled_pixel_start:compiled_pixel_end]
    original_non_pixel_prefix = bytes(orig_gim_data[:original_pixel_start])
    original_non_pixel_suffix = bytes(orig_gim_data[original_pixel_end:])
    orig_gim_data[original_pixel_start:original_pixel_end] = compiled_pixels
    if bytes(orig_gim_data[:original_pixel_start]) != original_non_pixel_prefix:
        raise RuntimeError("GIM header changed outside the pixel payload")
    if bytes(orig_gim_data[original_pixel_end:]) != original_non_pixel_suffix:
        raise RuntimeError("GIM palette/metadata changed outside the pixel payload")
    print(
        f"Injected {len(compiled_pixels):,} pixel bytes at "
        f"{original_pixel_start:#x}:{original_pixel_end:#x}; "
        "original palette and metadata preserved."
    )
    
    # Overwrite GIM bytes inside global_bytes array in-place!
    global_bytes[font_record["offset"] : font_record["offset"] + font_record["size"]] = orig_gim_data
    
    # Write patched global.res to working PSP_GAME
    dest_global_path = os.path.join(output_resource_root, "global", "global.res")
    os.makedirs(os.path.dirname(dest_global_path), exist_ok=True)
    with open(dest_global_path, "wb") as f_out:
        f_out.write(global_bytes)
    print(f"🎉 Patched global.res written successfully to: {dest_global_path}")
    
    # 4. Start again from the clean original tbldata.res loaded above.
    tbldata_bytes = bytearray(original_tbldata_bytes)
        
    tbldata_records = parse_res_header(tbldata_bytes)
    
    # Parse translation unified CSV for strings
    translation_data = {}
    with open(total_csv_path, "r", encoding="utf-8-sig") as csv_f:
        reader = csv.DictReader(csv_f)
        for row in reader:
            file_path = row["File Path"]
            string_idx = int(row["Index"])
            offset = int(row["Offset"])
            original = row["Original"].replace('\r\n', '\n')
            translated = row["Translated"].replace('\r\n', '\n')
            
            # File name is the last component, e.g. "amstrtbl" from "tbldata/tbldata_extracted/amstrtbl"
            file_name = file_path.split("/")[-1].lower()
            
            if file_name not in translation_data:
                translation_data[file_name] = []
                
            translation_data[file_name].append({
                "index": string_idx,
                "offset": offset,
                "original": original,
                "translated": translated
            })
            
    # Locate records and patch them in-place in tbldata.res
    print("\nPatching individual tables in-place in tbldata.res...")
    for record in tbldata_records:
        rec_name = record["name"].lower()
        rec_offset = record["offset"]
        rec_size = record["size"]
        
        # 4a. Handle fonttbl (update mapping table with safe Shift-JIS sequences)
        if rec_name == "fonttbl":
            print(f"  Patching 'fonttbl' at offset {hex(rec_offset)}, Size: {rec_size} bytes...")
            orig_tbl_bytes = bytearray(tbldata_bytes[rec_offset : rec_offset + rec_size])
            
            # Patch the exact entry whose index equals the rendered GIM tile.
            # Writing sequentially at 0x50 while rendering from tile 80 caused
            # the observed 80-glyph displacement (Hangul mixed with ｃ/７/Ｉ).
            for char in font_chars:
                char_bytes = char_to_sjis[char]
                map_offset = double_offset + char_to_tile[char] * 2
                orig_tbl_bytes[map_offset : map_offset + 2] = char_bytes
                
            tbldata_bytes[rec_offset : rec_offset + rec_size] = orig_tbl_bytes
            
        # 4b. Handle text databases (amstrtbl, btstrtbl, etc.)
        elif rec_name in translation_data:
            print(f"  Patching text table '{rec_name}' at offset {hex(rec_offset)}, Size: {rec_size} bytes...")
            strings = translation_data[rec_name]
            strings.sort(key=lambda x: x["index"])
            
            # Preserve the outer RESC record size, but rebuild every internal
            # STTV pointer/length so translations may borrow free space from
            # shorter strings in the same table without truncation.
            orig_stt_data = tbldata_bytes[rec_offset : rec_offset + rec_size]
            if rec_name == "etstrtbl":
                korean_stt_bin, rebuild_stats = patch_sttv1_preserving_slots(
                    orig_stt_data, strings, char_to_sjis
                )
            else:
                korean_stt_bin, rebuild_stats = rebuild_sttv1_in_fixed_record(
                    orig_stt_data, strings, char_to_sjis
                )
            if len(korean_stt_bin) != rec_size:
                raise RuntimeError(f"{rec_name}: rebuilt STTV changed record size")
            print(
                f"    Reflowed {len(strings)} strings without truncation; "
                f"{rebuild_stats['expanded_slots']} exceeded their old slots, "
                f"{rebuild_stats['remaining_bytes']} trailing bytes remain."
            )
                    
            # Overwrite inside tbldata_bytes array in-place!
            tbldata_bytes[rec_offset : rec_offset + rec_size] = korean_stt_bin
            
    # Write patched tbldata.res to working PSP_GAME
    dest_tbl_path = os.path.join(output_resource_root, "tbldata", "tbldata.res")
    os.makedirs(os.path.dirname(dest_tbl_path), exist_ok=True)
    with open(dest_tbl_path, "wb") as f_out:
        f_out.write(tbldata_bytes)
        
    print(f"🎉 Patched tbldata.res written successfully to: {dest_tbl_path}")

    # TSQV scenario data is rebuilt and repacked by the dedicated pipeline.
    # Do not leave the obsolete two-line fixed-slot test in the working tree.
    print("\n--- ⚡ ALL IN-PLACE PATCHES COMPLETED SUCCESSFULLY ⚡ ---")

if __name__ == "__main__":
    patch_in_place()
