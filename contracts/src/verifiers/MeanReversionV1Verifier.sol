// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        12_805_857_634_545_773_973_800_307_355_555_713_429_793_483_008_915_638_658_353_757_612_551_669_501_027;
    uint256 constant deltax2 =
        5_830_199_894_660_750_067_707_645_425_619_051_114_006_494_164_933_511_010_578_474_813_793_861_195_275;
    uint256 constant deltay1 =
        17_685_466_686_586_289_847_069_830_127_596_759_384_830_711_338_762_496_513_419_906_507_816_099_512_540;
    uint256 constant deltay2 =
        3_472_222_384_268_946_334_574_619_527_965_672_239_860_676_368_066_117_475_346_686_804_382_112_067_576;

    uint256 constant IC0x =
        11_758_260_767_508_535_102_423_787_494_387_667_779_506_737_891_710_914_418_920_477_239_990_510_474_457;
    uint256 constant IC0y =
        4_325_860_021_210_011_189_812_773_026_649_474_711_122_264_923_920_140_741_417_431_373_058_453_727_024;

    uint256 constant IC1x =
        772_906_364_050_968_808_849_153_163_408_159_931_206_698_489_064_912_542_034_945_968_153_191_408_413;
    uint256 constant IC1y =
        4_591_407_066_077_770_684_113_045_701_437_695_474_782_081_622_206_508_604_868_015_642_045_924_346_528;

    uint256 constant IC2x =
        20_031_731_923_246_672_493_712_367_395_683_239_802_680_810_057_794_873_561_468_748_973_403_514_028_676;
    uint256 constant IC2y =
        21_502_665_889_552_150_370_470_595_330_915_799_124_425_393_169_781_600_674_299_101_067_834_101_887_737;

    uint256 constant IC3x =
        7_823_874_013_814_785_084_111_600_623_595_331_723_141_251_740_896_126_039_005_639_756_018_935_305_446;
    uint256 constant IC3y =
        5_760_913_895_160_213_963_619_446_703_291_156_222_525_336_133_680_246_736_424_459_531_361_021_055_589;

    uint256 constant IC4x =
        4_142_319_505_530_120_891_355_593_088_119_869_262_016_944_743_731_699_874_860_058_443_802_758_567_479;
    uint256 constant IC4y =
        8_600_004_018_677_148_934_676_423_520_076_246_835_562_704_990_199_201_316_396_546_351_066_377_051_358;

    uint256 constant IC5x =
        5_539_215_965_930_410_168_829_036_091_048_804_931_151_234_541_134_740_274_543_621_010_463_752_270_592;
    uint256 constant IC5y =
        3_872_954_074_666_746_028_089_794_856_896_749_460_892_553_302_527_641_741_002_240_396_556_951_699_186;

    uint256 constant IC6x =
        17_441_414_587_693_443_362_487_239_597_770_804_705_037_001_649_995_276_280_242_273_448_084_058_803_207;
    uint256 constant IC6y =
        550_183_615_728_297_354_356_352_383_923_906_175_005_823_194_357_518_333_183_377_003_041_812_704_435;

    uint256 constant IC7x =
        6_909_999_080_947_049_166_985_121_571_093_775_853_133_640_894_691_564_524_286_846_647_934_146_206_393;
    uint256 constant IC7y =
        12_638_732_246_323_503_765_601_007_918_131_150_894_395_293_828_861_367_273_522_701_443_697_813_504_609;

    uint256 constant IC8x =
        844_113_715_198_662_405_553_872_042_202_293_087_340_745_530_289_374_132_034_695_431_858_110_024_738;
    uint256 constant IC8y =
        16_116_157_786_814_412_811_280_982_506_612_481_279_681_285_690_630_965_446_062_481_771_859_389_035_817;

    uint256 constant IC9x =
        18_313_082_638_876_635_683_674_587_397_296_008_080_030_453_750_297_321_981_107_058_293_441_148_683_172;
    uint256 constant IC9y =
        7_866_500_504_746_598_394_081_959_283_532_755_158_121_848_155_728_499_467_234_105_343_906_260_812_925;

    uint256 constant IC10x =
        2_851_357_757_219_320_481_933_613_188_752_673_213_149_583_602_098_445_302_799_873_063_831_773_273_303;
    uint256 constant IC10y =
        17_180_297_564_629_303_192_829_658_306_185_085_767_700_068_458_218_455_640_890_518_064_031_688_611_681;

    uint256 constant IC11x =
        3_425_955_650_412_028_969_681_445_272_104_963_537_646_427_566_530_610_619_939_053_415_591_891_613_967;
    uint256 constant IC11y =
        11_986_510_115_077_612_155_822_133_237_039_522_650_057_836_298_132_492_120_551_056_712_208_316_772_894;

    uint256 constant IC12x =
        9_436_970_045_996_528_411_856_505_018_153_229_135_353_288_888_286_214_950_233_343_651_057_321_684_235;
    uint256 constant IC12y =
        17_930_021_704_846_238_388_901_568_379_196_924_005_734_757_520_567_787_940_795_397_938_987_176_106_194;

    uint256 constant IC13x =
        5_376_030_554_482_429_220_992_753_441_386_253_141_673_098_513_860_215_345_783_585_577_549_908_526_430;
    uint256 constant IC13y =
        3_727_001_499_447_068_209_277_551_266_509_589_584_114_327_073_926_089_429_282_811_180_818_847_122_251;

    uint256 constant IC14x =
        16_145_884_693_673_110_417_807_694_145_887_051_787_904_973_249_757_310_614_685_619_004_744_422_336_081;
    uint256 constant IC14y =
        16_679_149_375_761_399_598_723_559_426_937_500_093_501_202_413_759_576_478_043_358_303_437_121_349_818;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
