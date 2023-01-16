def calculate_storage(filesize):
    block_size = 4096
    full_blocks = filesize // block_size
    resultado_modulo = filesize % block_size
    if resultado_modulo > 0 :
        return ((full_blocks * block_size) + block_size)
    return (full_blocks * block_size)
print (calculate_storage(1))
print (calculate_storage(4096))
print (calculate_storage(4097))
print (calculate_storage(6000))
