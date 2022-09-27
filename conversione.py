from osgeo import gdal, ogr
import numpy as np
import os
import requests
tmp_path = "/tmp"

input_path = tmp_path + "/DSM.gtif"        # che viene estratta dallo zip
output_path = tmp_path + "/DSM_cog.gtif"

class ValidateCloudOptimizedGeoTIFFException(Exception):
    pass

def validate(ds, check_tiled=True):
    """Check if a file is a (Geo)TIFF with cloud optimized compatible structure.
    Args:
      ds: GDAL Dataset for the file to inspect.
      check_tiled: Set to False to ignore missing tiling.
    Returns:
      A tuple, whose first element is an array of error messages
      (empty if there is no error), and the second element, a dictionary
      with the structure of the GeoTIFF file.
    Raises:
      ValidateCloudOptimizedGeoTIFFException: Unable to open the file or the
        file is not a Tiff.
    """

    if int(gdal.VersionInfo('VERSION_NUM')) < 2020000:
        raise ValidateCloudOptimizedGeoTIFFException(
            'GDAL 2.2 or above required')

    unicode_type = type(''.encode('utf-8').decode('utf-8'))
    if isinstance(ds, str) or isinstance(ds, unicode_type):
        gdal.PushErrorHandler()
        ds = gdal.Open(ds)
        gdal.PopErrorHandler()
        if ds is None:
            raise ValidateCloudOptimizedGeoTIFFException(
                'Invalid file : %s' % gdal.GetLastErrorMsg())
        if ds.GetDriver().ShortName != 'GTiff':
            raise ValidateCloudOptimizedGeoTIFFException(
                'The file is not a GeoTIFF')

    details = {}
    errors = []
    filename = ds.GetDescription()
    main_band = ds.GetRasterBand(1)
    ovr_count = main_band.GetOverviewCount()
    filelist = ds.GetFileList()
    if filelist is not None and filename + '.ovr' in filelist:
        errors += [
            'Overviews found in external .ovr file. They should be internal']

    if main_band.XSize >= 512 or main_band.YSize >= 512:
        if check_tiled:
            block_size = main_band.GetBlockSize()
            if block_size[0] == main_band.XSize and block_size[0] > 1024:
                errors += [
                    'The file is greater than 512xH or Wx512, but is not tiled']

        if ovr_count == 0:
            errors += [
                'The file is greater than 512xH or Wx512, but has no overviews']

    ifd_offset = int(main_band.GetMetadataItem('IFD_OFFSET', 'TIFF'))
    ifd_offsets = [ifd_offset]
    if ifd_offset not in (8, 16):
        errors += [
            'The offset of the main IFD should be 8 for ClassicTIFF '
            'or 16 for BigTIFF. It is %d instead' % ifd_offsets[0]]
    details['ifd_offsets'] = {}
    details['ifd_offsets']['main'] = ifd_offset

    for i in range(ovr_count):
        # Check that overviews are by descending sizes
        ovr_band = ds.GetRasterBand(1).GetOverview(i)
        if i == 0:
            if (ovr_band.XSize > main_band.XSize or
                ovr_band.YSize > main_band.YSize):
                    errors += [
                        'First overview has larger dimension than main band']
        else:
            prev_ovr_band = ds.GetRasterBand(1).GetOverview(i-1)
            if (ovr_band.XSize > prev_ovr_band.XSize or
                ovr_band.YSize > prev_ovr_band.YSize):
                    errors += [
                        'Overview of index %d has larger dimension than '
                        'overview of index %d' % (i, i-1)]

        if check_tiled:
            block_size = ovr_band.GetBlockSize()
            if block_size[0] == ovr_band.XSize and block_size[0] > 1024:
                errors += [
                    'Overview of index %d is not tiled' % i]

        # Check that the IFD of descending overviews are sorted by increasing
        # offsets
        ifd_offset = int(ovr_band.GetMetadataItem('IFD_OFFSET', 'TIFF'))
        ifd_offsets.append(ifd_offset)
        details['ifd_offsets']['overview_%d' % i] = ifd_offset
        if ifd_offsets[-1] < ifd_offsets[-2]:
            if i == 0:
                errors += [
                    'The offset of the IFD for overview of index %d is %d, '
                    'whereas it should be greater than the one of the main '
                    'image, which is at byte %d' %
                    (i, ifd_offsets[-1], ifd_offsets[-2])]
            else:
                errors += [
                    'The offset of the IFD for overview of index %d is %d, '
                    'whereas it should be greater than the one of index %d, '
                    'which is at byte %d' %
                    (i, ifd_offsets[-1], i-1, ifd_offsets[-2])]

    # Check that the imagery starts by the smallest overview and ends with
    # the main resolution dataset
    block_offset = main_band.GetMetadataItem('BLOCK_OFFSET_0_0', 'TIFF')
    if not block_offset:
        errors += ['Missing BLOCK_OFFSET_0_0']
    data_offset = int(block_offset) if block_offset else None
    data_offsets = [data_offset]
    details['data_offsets'] = {}
    details['data_offsets']['main'] = data_offset
    for i in range(ovr_count):
        ovr_band = ds.GetRasterBand(1).GetOverview(i)
        data_offset = int(ovr_band.GetMetadataItem('BLOCK_OFFSET_0_0', 'TIFF'))
        data_offsets.append(data_offset)
        details['data_offsets']['overview_%d' % i] = data_offset

    if data_offsets[-1] < ifd_offsets[-1]:
        if ovr_count > 0:
            errors += [
                'The offset of the first block of the smallest overview '
                'should be after its IFD']
        else:
            errors += [
                'The offset of the first block of the image should '
                'be after its IFD']
    for i in range(len(data_offsets)-2, 0, -1):
        if data_offsets[i] < data_offsets[i + 1]:
            errors += [
                'The offset of the first block of overview of index %d should '
                'be after the one of the overview of index %d' %
                (i - 1, i)]
    if len(data_offsets) >= 2 and data_offsets[0] < data_offsets[1]:
        errors += [
            'The offset of the first block of the main resolution image'
            'should be after the one of the overview of index %d' %
            (ovr_count - 1)]

    return errors, details
    
def check_valid(filename):
    try:
        errors, _ = validate(filename)
        if errors:
            print('%s is NOT a valid cloud optimized GeoTIFF.' % filename)
            print('The following errors were found:')
            for error in errors:
                print(' - ' + error)
            ret = 1
        else:
            ret = 0
            print('%s is a valid cloud optimized GeoTIFF' % filename)
    except ValidateCloudOptimizedGeoTIFFException as e:
        print('%s is NOT a valid cloud optimized GeoTIFF : %s' % (filename, str(e)))
        ret = 1
    return ret

def download_file(url):
    print('Downloading started')

    # Downloading the file by sending the request to the URL
    req = requests.get(url)
    print('Downloading Completed')
    
    with open(input_path, "wb") as f:
        f.write(req.content)
    return

def conversione(input, output):
    orig_ds = gdal.Open(input)
    x_size=orig_ds.RasterXSize
    y_size=orig_ds.RasterYSize
    num_bands = 1

    data = np.ones((num_bands, y_size, x_size))
    data_set = gdal.GetDriverByName('MEM').Create('', x_size, y_size, num_bands,gdal.GDT_Float32)
    
    for i in range(num_bands):
        data_set.GetRasterBand(i + 1).WriteArray(data[i])

    data = None
    data_set.BuildOverviews("NEAREST", [2, 4, 8, 16, 32, 64])

    data_set2 = gdal.GetDriverByName('GTiff').CreateCopy(output, data_set,options=["COPY_SRC_OVERVIEWS=YES","TILED=YES","COMPRESS=LZW"])
    data_set = None
    data_set2 = None
    return

def run (url):
    print("Avvio download")
    # download file
    download_file(url)
    # converto il file in cog
    conversione(input_path, output_path)
    # valido il file cog
    print(str(check_valid(output_path)))
    return
