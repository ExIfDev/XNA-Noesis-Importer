#Written by Aexadev on 21/07/2025
#ver 0.3.1
from inc_noesis import *  
import noesis, rapi, struct 


DEBUG = False
DUMP=False

HIDEF_MASK = 0x01
COMPRESSED_LZX_MASK = 0x80
COMPRESSED_LZ4_MASK = 0x40

def registerNoesisTypes():
 
    hTex = noesis.register("XNA Texture", ".xnb")
    noesis.setHandlerTypeCheck(hTex, ChkXnbTexture)
    noesis.setHandlerLoadRGBA( hTex, LoadAsset) 

  
    hMdl = noesis.register("XNA Model", ".xnb")
    noesis.setHandlerTypeCheck(hMdl, ChkXnbModel)
    noesis.setHandlerLoadModel(hMdl, LoadAsset)  

    return 1

def ChkXnbTexture(data):
    if data[:3] != b"XNB":
        return False
    return "Texture2DReader" in getFileType(data)

def ChkXnbModel(data):
    if data[:3] != b"XNB":
        return False
    return "ModelReader" in getFileType(data)

class XNBHeader:
    def __init__(self, data):
        self.raw = data
        self.hidef = False
        self.compressed = False
        self.comp_type = 0
        self.payload = b""
        self._parse()

    def _parse(self):
        bs = NoeBitStream(self.raw, NOE_LITTLEENDIAN)
        magic = bs.readBytes(3)
        if magic != b"XNB":
            noesis.doException("Invalid XNB header")

        self.platform = bs.readByte()
        version = bs.readByte()
        flags = bs.readByte()

        self.hidef = (flags & HIDEF_MASK) != 0
        self.compressed = bool(flags & (COMPRESSED_LZX_MASK | COMPRESSED_LZ4_MASK))
        self.comp_type = flags & (COMPRESSED_LZX_MASK | COMPRESSED_LZ4_MASK)

        file_size = bs.readUInt()

        if self.compressed:
            real_size = bs.readUInt()
            comp_len = file_size - 14
            comp_data = bs.readBytes(comp_len)

            if self.comp_type == COMPRESSED_LZ4_MASK:
                self.payload = rapi.decompLZ4(comp_data, real_size)
            elif self.comp_type == COMPRESSED_LZX_MASK:
                self.payload = rapi.decompXMemLZX(comp_data, real_size, 16, -1, -1)
            else:
                noesis.doException("Unsupported compression type")
        else:
            self.payload = self.raw[10:]  


def LoadAsset(data, outList):
    rapi.rpgCreateContext()
    header = XNBHeader(data)
    bs = NoeBitStream(header.payload, NOE_LITTLEENDIAN)

    reader_cnt  = read_7bit_encoded_int(bs)
    readers     = []
    for _ in range(reader_cnt):
        name_len   = read_7bit_encoded_int(bs)
        reader_nm  = bs.readBytes(name_len).decode("utf-8")
        version    = bs.readUInt()
        readers.append(reader_nm)

    shared_cnt = read_7bit_encoded_int(bs)
    root_reader = readers[0]
    if outList is None:
        outList = []

    if "Texture2DReader" in root_reader:
        Texture2DReader(bs, outList, header)
    elif "ModelReader"     in root_reader:
        ModelReader(bs, outList)

    return 1


def Texture2DReader(bs, texList, header):
    reader_idx = readToken(bs)
    if reader_idx is None:    
        return    
    surf_fmt = bs.readUInt()
    width = bs.readUInt()
    height = bs.readUInt()
    mip_cnt = bs.readUInt()
    data_len = bs.readUInt()
    img_data = bs.readBytes(data_len)

    if DEBUG:
        print("[TEX] %dx%d  fmt=%d  len=%d" % (width, height, surf_fmt, data_len))

    if surf_fmt == 0:
        if header.platform == 120:
            rgba = rapi.imageDecodeRaw(img_data, width, height, "a8b8g8r8")#xbox360
        else:
            rgba = rapi.imageDecodeRaw(img_data, width, height, "r8g8b8a8")#pc
    elif surf_fmt == 4:
        rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT1)
    elif surf_fmt == 5:
        rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT3)
    elif surf_fmt == 6:
        rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT5)
    else:
        noesis.doException("Unsupported SurfaceFormat: %d" % surf_fmt)
        return

    byte_rgba = bytearray(rgba)
    for i in range(0, len(byte_rgba), 4):
        a = byte_rgba[i + 3]
        if a not in (0, 255):
            inv = 255.0 / a
            byte_rgba[i] = min(int(byte_rgba[i] * inv + 0.5), 255)
            byte_rgba[i + 1] = min(int(byte_rgba[i + 1] * inv + 0.5), 255)
            byte_rgba[i + 2] = min(int(byte_rgba[i + 2] * inv + 0.5), 255)

    tex = NoeTexture("xnb_tex", width, height, bytes(byte_rgba), noesis.NOESISTEX_RGBA32)
    texList.append(tex)
    return 1



def ModelReader(bs, mdlList):
    rapi.rpgSetOption(noesis.RPGOPT_SWAPHANDEDNESS, 1)#LEFT HANDED
    def read_bone_reference(bs, bone_count):
        if bone_count > 255:
            ref_id = bs.readInt()
        else:
            ref_id = bs.readByte()
        if ref_id == 0:
            return None
        return ref_id - 1
    if DUMP:
        try:
            dump_dir = r""
            if not os.path.exists(dump_dir):
                os.makedirs(dump_dir)
            offset = bs.getOffset()
            dump_path = os.path.join(dump_dir, "model_dump_%X.bin" % offset)

            with open(dump_path, "wb") as f:
                f.write(bs.getBuffer()) 

            print("[DUMP] Decompressed model dumped to: %s" % dump_path)
        except Exception as e:
            print("[ERROR] Failed to dump model payload: %s" % str(e))

    reader_idx = readToken(bs)
    if reader_idx is None:
        return

    boneCount = bs.readInt()
    print("[MODEL] Bone count: %d" % boneCount)

    names, parents = [], []
    matrices = []

    for i in range(boneCount):
        token = read_7bit_encoded_int(bs)
        if token == 0:
            bName = "bone_%d" % i
        else:
            name_len = read_7bit_encoded_int(bs)
            bName = bs.readBytes(name_len).decode("utf-8", "ignore")
        mat_floats = [bs.readFloat() for _ in range(16)]

        rows = [
                NoeVec4(mat_floats[0:4]),
                NoeVec4(mat_floats[4:8]),
                NoeVec4(mat_floats[8:12]),
                NoeVec4(mat_floats[12:16])
            ]
        mat = NoeMat44(rows).toMat43()

        names.append(bName)
        matrices.append(mat)

    for i in range(boneCount):
        parent_index = read_bone_reference(bs, boneCount)
        parents.append(parent_index if parent_index is not None else -1)

        child_count = bs.readInt()
        for _ in range(child_count):
            _ = read_bone_reference(bs, boneCount) 
            
    # Read meshes
    meshCount = bs.readUInt()
    print("MeshCnt ",meshCount)
    for i in range (meshCount):
        token = read_7bit_encoded_int(bs)
        if token == 0:
            mName = "mesh_%d" % i
        else:
            mame_len = read_7bit_encoded_int(bs)
            mName = bs.readBytes(mame_len).decode("utf-8", "ignore")
        parentBone = read_bone_reference(bs,boneCount)
        print("MESH ",mName)
        print("PB ",parentBone)
        #bound sphere
        bs.seek(16,NOESEEK_REL)#vec3 center + float radius
        print(bs.getOffset())
        
        read_7bit_encoded_int(bs)
        
        #ReadMeshParts
        meshPartCount = bs.readInt()
        print("MPC ",meshPartCount)
        for i in range (meshPartCount):
            vertexOff = bs.readInt()
            vertexCnt = bs.readInt()
            startIndex= bs.readInt()
            primCount= bs.readInt() 
            read_7bit_encoded_int(bs)
            print(vertexOff)
            print(vertexCnt)
        #(TODO)MESH VERTEX BUFFER, PRIMITIVE BUFFER, EFFECT BUFFER ARE UNIMPLEMENTED
        """
        public enum VertexElementFormat
        {
            Single,
            Vector2,
            Vector3,
            Vector4,
            Color,
            Byte4,
            Short2,
            Short4,
            NormalizedShort2,
            NormalizedShort4,
            HalfVector2,
            HalfVector4
        }
        """    
    noeBones = []
    for i in range(boneCount):
        bone = NoeBone(i, names[i], matrices[i], None, parents[i])
        noeBones.append(bone)
    noeBones = rapi.multiplyBones(noeBones)  
    
    mdl = NoeModel()
    mdl.setBones(noeBones)
    mdlList.append(mdl)
    rapi.setPreviewOption("setSkelToShow", "1")


def getFileType(data):
    try:
        hdr   = XNBHeader(data)                       
        bs    = NoeBitStream(hdr.payload, NOE_LITTLEENDIAN)
        rcnt  = read_7bit_encoded_int(bs)
        if rcnt == 0:
            return ""
        nameLen   = read_7bit_encoded_int(bs)
        readerStr = bs.readBytes(nameLen).decode("utf-8", "ignore")
        return readerStr
    except:
        return ""
def read_7bit_encoded_int(bs, max_bytes=5):
    result = 0
    shift = 0
    for i in range(max_bytes):
        if bs.getOffset() >= len(bs.getBuffer()):
            raise ValueError("Unexpected end of stream.")
        b = bs.readUByte()
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result
        shift += 7
    raise ValueError("Err1 Infinite loop watchdog triggered, unsupported file")


def readToken(bs):
    token = read_7bit_encoded_int(bs)
    if token == 0:
        return None           
    return token - 1      







