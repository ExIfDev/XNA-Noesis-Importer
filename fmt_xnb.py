#Written by Aexadev on 28/07/2025

from inc_noesis import *  
import noesis, rapi, struct  # type: ignore
import os, time, zipfile, traceback

DEBUG = 0
HIDEF_MASK  = 0x01
COMPRESSED_LZX_MASK = 0x80
COMPRESSED_LZ4_MASK = 0x40

PluginVer = "0.4.3"

#NOESIS 
def registerNoesisTypes():
 
    hTex = noesis.register("XNA Texture2D", ".xnb")
    noesis.setHandlerTypeCheck(hTex, ChkXnbTexture)
    noesis.setHandlerLoadRGBA( hTex, LoadAsset) 
    
    hMdl = noesis.register("XNA Model", ".xnb")
    noesis.setHandlerTypeCheck(hMdl, ChkXnbModel)
    noesis.setHandlerLoadModel(hMdl, LoadAsset)  
  
    hSpr = noesis.register("XNA SpriteFont", ".xnb")
    noesis.setHandlerTypeCheck(hSpr, ChkXnbSpriteFont)
    noesis.setHandlerLoadRGBA(hSpr, LoadAsset)
    
    hSnd = noesis.register("XNA SoundEffect", ".xnb")
    noesis.setHandlerTypeCheck(hSnd, ChkXnbSound)
    noesis.setHandlerLoadRGBA(hSnd, LoadAsset)
    
    hEff = noesis.register("XNA Effect", ".xnb")
    noesis.setHandlerTypeCheck(hEff, ChkXnbEffect)
    noesis.setHandlerLoadRGBA(hEff, LoadAsset)
    


    return 1

def ChkXnbTexture(data):
    if data[:3] != b"XNB":
        return False
    return "Texture2DReader" in getFileType(data)


def ChkXnbSpriteFont(data):
    if data[:3] != b"XNB":
        return False
    return "SpriteFont" in getFileType(data)

def ChkXnbModel(data):
    if data[:3] != b"XNB":
        return False
    return "ModelReader" in getFileType(data)

def ChkXnbSound(data):
    if data[:3] != b"XNB":
        return False
    return "SoundEffect" in getFileType(data)
def ChkXnbEffect(data):
    if data[:3] != b"XNB":
        return False
    return "Effect" in getFileType(data)




#ASSET TYPE RESOLVER
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
        self.version = bs.readByte()
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
    root_index = readToken(bs)
    if root_index is None or root_index < 0 or root_index >= len(readers):
        noesis.doException("Invalid root reader index")
        return 0

    native_reader = getNativeReader(readers, root_index)
    if native_reader is None:
        noesis.doException("Could not resolve reader")
        return 0

    print("Root reader:", readers[root_index])
    print("Chosen reader:", native_reader)
    if readers[root_index] != native_reader:
        bs.seek(1,NOESEEK_REL)

    reader = native_reader


    if outList is None:
        outList = []

    if "Texture2DReader" in reader:
        Texture2DReader(bs, outList, header)      # token already consumed
    elif "ModelReader" in reader:
        ModelReader(bs, outList, header)          # token already consumed
    elif "SpriteFont" in reader:
        noesis.messagePrompt("SpriteFont asset is not currently supported!")
        return 0
    elif "SoundEffect" in reader:
        noesis.messagePrompt("SoundEffect asset is not currently supported!")
        return 0
    elif "Effect" in reader:
        noesis.messagePrompt("Effect asset is not currently supported!")
        return 0
    else:
        noesis.doException("Unsupported root reader: %s" % reader)
        return 0

    return 1


#READERS
def Texture2DReader(bs, texList,header):
    try :   
        
        def unmultiplyAlpha(rgba):
            byte_rgba = bytearray(rgba)
            for i in range(0, len(byte_rgba), 4):
                a = byte_rgba[i + 3]
                if a not in (0, 255):
                    inv = 255.0 / a
                    byte_rgba[i] = min(int(byte_rgba[i] * inv + 0.5), 255)
                    byte_rgba[i + 1] = min(int(byte_rgba[i + 1] * inv + 0.5), 255)
                    byte_rgba[i + 2] = min(int(byte_rgba[i + 2] * inv + 0.5), 255)
            return byte_rgba
        
        surf_fmt = bs.readUInt()
        width = bs.readUInt()
        height = bs.readUInt()
        mip_cnt = bs.readUInt()
        data_len = bs.readUInt()
        print(bs.getOffset())
        img_data = bs.readBytes(data_len)

        if DEBUG:
            noesis.logPopup()
            print("[TEX] %dx%d  fmt=%d  len=%d" % (width, height, surf_fmt, data_len))

        if surf_fmt == 0:
            if header.platform == 120:#xbox360
                rgbma = rapi.imageDecodeRaw(img_data, width, height, "a8b8g8r8")
                rgba = unmultiplyAlpha(rgbma)
            else: 
                rgbma = rapi.imageDecodeRaw(img_data, width, height, "r8g8b8a8")
                rgba = unmultiplyAlpha(rgbma)
                
        elif surf_fmt ==1:
            if header.platform == 120:
                rgba = rapi.imageDecodeRaw(img_data, width, height, "a8b8g8r8")
                
            else:
                noesis.messagePrompt("Surface Format 1 for this platform is not supported")
                

        elif surf_fmt == 4 or surf_fmt==28:
            if header.platform == 120:  # Xbox 360
                big_endian_data = rapi.swapEndianArray(img_data, 2)
                rgba = rapi.imageDecodeDXT(big_endian_data, width, height, noesis.FOURCC_DXT1)
            else:
                rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT1)
                
        elif surf_fmt == 5  :
            #	PYNOECONSTN(NOEBLEND_NONE),
            

            if header.platform == 120:#xbox360
                big_endian_data = rapi.swapEndianArray(img_data, 2)
                rgba = rapi.imageDecodeDXT(big_endian_data, width, height, noesis.FOURCC_DXT3)
            else:
                rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT3)
                
        elif surf_fmt == 6 or surf_fmt==32:
            
        
            if header.platform == 120:#xbox360
                big_endian_data = rapi.swapEndianArray(img_data, 2)
                rgba = rapi.imageDecodeDXT(big_endian_data, width, height, noesis.FOURCC_DXT5)
            else:
                rgba = rapi.imageDecodeDXT(img_data, width, height, noesis.FOURCC_DXT5)
            
        else:
            noesis.doException("Unsupported SurfaceFormat: %d" % surf_fmt)
            return

        tex = NoeTexture("xnb_tex", width, height, bytes(rgba), noesis.NOESISTEX_RGBA32)
        texList.append(tex)

        return 1
    except Exception as e:
        print(e)
        if DEBUG == False: 
            path = noesis.userPrompt( noesis.NOEUSERVAL_FOLDERPATH,
                                    "We have hit an error! Please create the debug dump or close.",
                                    "Please enter a save path for the debug file then submit to the developer",
                                    )
            dat= ("Exception hit in Texture2DReader",e,"PluginVer",PluginVer,"surfFmt",surf_fmt,"width",width,
                "height",height,"mip",mip_cnt,"PLATFORM",header.platform,"XNA version",header.version)
            if path:      
                fn = os.path.basename(rapi.getInputName())
                with open (rapi.getInputName(),"rb") as f:
                    ogfile = f.read()
                fname = fn[:-3] + "bin"
                ds={
                    fname: bs.getBuffer(),#decompressed stream
                    os.path.basename(rapi.getInputName()):ogfile
                    
                }
                debugData(path,dat,ds)
        
    


def ModelReader(bs, mdlList,header):
    try:
        
    
        print(header.platform)
        if header.platform!= 119:
            noesis.messagePrompt("Only unskinned models for the PC platform are supported!")
            return
        rapi.rpgSetOption(noesis.RPGOPT_SWAPHANDEDNESS, 1)#LEFT HANDED
        
        def read_bone_reference(bs, bone_count):
            if bone_count > 255:
                ref_id = bs.readInt()
            else:
                ref_id = bs.readByte()
            if ref_id == 0:
                return None
            return ref_id - 1


        boneCount = bs.readInt()
        print("[MDL] BONE_COUNT: %d" % boneCount)

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
            print("[MDL] [",i,"]" ,bName)
            matrices.append(mat)

        for i in range(boneCount):
            parent_index = read_bone_reference(bs, boneCount)
            parents.append(parent_index if parent_index is not None else -1)

            child_count = bs.readInt()
            for _ in range(child_count):
                _ = read_bone_reference(bs, boneCount) 
                
        # Read meshes--------------------------------
        meshCount = bs.readUInt()
        print("[MDL] MESH_COUNT: ",meshCount)
        for i in range (meshCount):
            token = read_7bit_encoded_int(bs)
            if token == 0:
                mName = "mesh_%d" % i
            else:
                mame_len = read_7bit_encoded_int(bs)
                mName = bs.readBytes(mame_len).decode("utf-8", "ignore")
            parentBone = read_bone_reference(bs,boneCount)
            print("[MDL] MESH_NAME: ",mName)
            print("[MDL] PARENT_BONE:",parentBone)
            #bound sphere
            bs.seek(16,NOESEEK_REL)#vec3 center + float radius
            print(bs.getOffset())
            
            read_7bit_encoded_int(bs)
            
            #ReadMeshParts
            meshPartCount = bs.readInt()
            print("[MDL] MESH_PT_CNT: ",meshPartCount)
            for i in range (meshPartCount):
                print("-- MESHIDX ",i)
                vertexOff = bs.readInt()
                vertexCnt = bs.readInt()
                startIndex= bs.readInt()
                primCount= bs.readInt() 
                
                print("--- VertOffset: ",vertexOff)
                print("--- VertCount : ",vertexCnt)
                print("--- StartIndex: ",startIndex)
                print("--- PrimCount : ",primCount)
                print(bs.getOffset())
            read_7bit_encoded_int(bs)   
            bs.seek(66,NOESEEK_REL)#unk data
            print(bs.getOffset())
            if boneCount <= 1:
                #noesis.messagePrompt("Skinned models are not supported yet")
                #return 0
            
                vertPos=[]
                uv=[]
                normals=[]
                for i in range(vertexCnt):#stride 
                    X=bs.readFloat()
                    Y=bs.readFloat()
                    Z=bs.readFloat()
                    vertPos.extend((X, Y, Z))
                    
                    nX=bs.readFloat()
                    nY=bs.readFloat()
                    nZ=bs.readFloat()
                    normals.extend((nX, nY, nZ))
                
                    
                    u=bs.readFloat()
                    v=bs.readFloat()
                    uv.extend((u,v))   
                    
                    
                bs.seek(6,NOESEEK_REL)#unk
                print(bs.getOffset())
                
                indices = []
                for i in range(primCount):
                    a=bs.readUShort()
                    b=bs.readUShort()
                    c=bs.readUShort()
                    indices.extend([a, b, c])
                import struct

            
                posBuf = struct.pack("<%df" % (len(vertPos)), *vertPos)
                idxBuf = struct.pack("<%dH" % len(indices), *indices)
                uvBuf = struct.pack("<%df" % len(uv), *uv)
                nrmBuf = struct.pack("<%df" % (len(normals)), *normals)

                rapi.rpgSetName(mName)                
        
                rapi.rpgBindPositionBuffer(posBuf, noesis.RPGEODATA_FLOAT, 12)
                rapi.rpgBindUV1Buffer(uvBuf, noesis.RPGEODATA_FLOAT, 8)
                rapi.rpgBindNormalBuffer  (nrmBuf, noesis.RPGEODATA_FLOAT, 12)


                rapi.rpgCommitTriangles(
                    idxBuf,                     
                    noesis.RPGEODATA_USHORT,   
                    len(indices),                
                    noesis.RPGEO_TRIANGLE      
                )

        noeBones = []
        for i in range(boneCount):
            bone = NoeBone(i, names[i], matrices[i], None, parents[i])
            noeBones.append(bone)
        noeBones = rapi.multiplyBones(noeBones)
        rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 1)

        mdl = rapi.rpgConstructModel()
        if mdl is None:
            mdl = NoeModel()

        mdl.setBones(noeBones)
        mdlList.append(mdl)
        rapi.setPreviewOption("setSkelToShow", "1")
    except Exception as e:
        print(e)
        if DEBUG == False: 
            path = noesis.userPrompt( noesis.NOEUSERVAL_FOLDERPATH,
                                    "We have hit an error! Please create the debug dump or close.",
                                    "Please enter a save path for the debug file then submit to the developer",
                                    )
            dat= ("Exception hit in ModelReader",e,"PluginVer",PluginVer,"PLATFORM",header.platform,"XNA version",header.version)
            if path:      
                fn = os.path.basename(rapi.getInputName())
                with open (rapi.getInputName(),"rb") as f:
                    ogfile = f.read()
                fname = fn[:-3] + "bin"
                ds={
                    fname: bs.getBuffer(),#decompressed stream
                    os.path.basename(rapi.getInputName()):ogfile
                    
                }
                debugData(path,dat,ds)
        

#HELPERS

def getFileType(data):
    try:
        hdr = XNBHeader(data)
        bs  = NoeBitStream(hdr.payload, NOE_LITTLEENDIAN)


        rcnt = read_7bit_encoded_int(bs)
        readers = []
        for _ in range(rcnt):
            name_len = read_7bit_encoded_int(bs)
            reader   = bs.readBytes(name_len).decode("utf-8", "ignore")
            print(reader)
            _ver     = bs.readUInt()
            readers.append(reader)

        _shared_cnt = read_7bit_encoded_int(bs)
        root_index  = readToken(bs)  # 0-based from your helper
        chosen = getNativeReader(readers, root_index)
        
        return chosen if chosen is not None else ""
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
def isNative(name: str) -> bool:

    return "Microsoft.Xna.Framework.Content" in name

def getNativeReader(readers, root_index):

    if root_index is None or root_index < 0 or root_index >= len(readers):
        return None

    root_reader = readers[root_index]
    if isNative(root_reader):
        return root_reader

    for i in range(root_index + 1, len(readers)):
        if isNative(readers[i]):
            return readers[i]


    return root_reader

#DEBUG

def _zip_compression():
    try:
        return zipfile.ZIP_DEFLATED
    except Exception:
        return zipfile.ZIP_STORED

def debugData(zip_dir, exception_text, extra_files=None, zip_name_prefix="!debugNoeFmtXnb"):
    if not zip_dir:
        zip_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(zip_dir):
        os.makedirs(zip_dir)

    ts = time.strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(zip_dir, "%s_%s.zip" % (zip_name_prefix, ts))

    comp = _zip_compression()
    with zipfile.ZipFile(zip_path, mode="w", compression=comp) as zf:
        text_to_write = "\n".join(map(str, exception_text)) 
        zf.writestr("exception.txt", text_to_write.encode("utf-8"))
        if extra_files:
            for arc_name, content in extra_files.items():
                if isinstance(content, bytes):
                    zf.writestr(arc_name, content)
                else:
                    zf.writestr(arc_name, str(content).encode("utf-8"))

    return zip_path



